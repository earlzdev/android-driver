"""YAML flows — the project's own test verbs, declared in config.

A recipe is a named sequence of steps a project runs over and over: sign in,
create an order, join a call. Written once in `.android-driver.yaml`, each one is
registered as a real MCP tool with typed parameters, so an agent sees
`login(email, password)` in its tool list rather than having to rediscover a
six-step flow from a screen dump every session.

    recipes:
      login:
        description: Sign in and land on the home screen
        params:
          email: {required: true}
          password: {required: true, secret: true}
        steps:
          - launch:
          - type: {id: email_field, text: "{{email}}"}
          - type: {id: password_field, text: "{{password}}"}
          - tap: "Sign in"
          - expect_visible: {text: Welcome, timeout_s: 20}

Steps run through the same `actions` functions the hand-driven tools use, so a
recipe cannot drift away from what an agent does interactively.
"""

from __future__ import annotations

import inspect
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import actions, adb, emulator, expect
from .config import Config
from .log import log
from .run import Runs
from .session import Session

MAX_RECIPE_DEPTH = 5
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
WHOLE_PLACEHOLDER_RE = re.compile(r"^\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}$")

PARAM_TYPES: dict[str, type] = {"str": str, "int": int, "float": float, "bool": bool}

# Keys on a step mapping that configure the step rather than the verb.
STEP_META = {"retry", "optional", "settle_s", "label"}

# Verbs whose single obvious argument can be written as a bare scalar.
SCALAR_ARG = {
    "sleep": "seconds",
    "press": "key",
    "shell": "cmd",
    "screenshot": "name",
    "launch": "pkg",
    "force_stop": "pkg",
    "clear_data": "pkg",
    "install": "apk_path",
    "snapshot_save": "name",
    "snapshot_load": "name",
    "expect_log": "pattern",
    "run": "recipe",
    "tap": "text",
    "long_press": "text",
    "scroll_to": "text",
    "expect_visible": "text",
    "expect_gone": "text",
}


class RecipeError(RuntimeError):
    """A recipe is malformed. Raised at load time, never mid-run."""


class StepFailed(RuntimeError):
    """A step failed at runtime. Carries the structured detail for the report."""

    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


# ── model ─────────────────────────────────────────────────────────────────────


@dataclass
class Param:
    name: str
    type: str = "str"
    required: bool = False
    default: Any = None
    description: str = ""
    secret: bool = False

    @property
    def py_type(self) -> type:
        return PARAM_TYPES[self.type]


@dataclass
class Step:
    verb: str
    args: dict[str, Any] = field(default_factory=dict)
    retry: int = 0
    optional: bool = False
    settle_s: float = 0.0
    label: str = ""

    @property
    def name(self) -> str:
        return self.label or self.verb


@dataclass
class Recipe:
    name: str
    description: str
    params: list[Param]
    steps: list[Step]
    on_failure: str = "stop"

    @property
    def param_map(self) -> dict[str, Param]:
        return {p.name: p for p in self.params}


def _parse_params(name: str, raw: Any) -> list[Param]:
    if raw is None:
        return []
    if isinstance(raw, list):  # shorthand: a list of required string params
        return [Param(name=str(p), required=True) for p in raw]
    if not isinstance(raw, dict):
        raise RecipeError(f"recipe {name!r}: `params` must be a mapping or a list, got {type(raw).__name__}")

    params: list[Param] = []
    for key, spec in raw.items():
        if not NAME_RE.match(str(key)):
            raise RecipeError(f"recipe {name!r}: {key!r} is not a valid parameter name (a-z, 0-9, _)")
        spec = spec or {}
        if not isinstance(spec, dict):
            spec = {"default": spec}
        unknown = set(spec) - {"type", "required", "default", "description", "secret"}
        if unknown:
            raise RecipeError(f"recipe {name!r}: parameter {key!r} has unknown key(s) {sorted(unknown)}")
        ptype = str(spec.get("type", "str"))
        if ptype not in PARAM_TYPES:
            raise RecipeError(
                f"recipe {name!r}: parameter {key!r} has type {ptype!r}; use one of {sorted(PARAM_TYPES)}"
            )
        params.append(
            Param(
                name=str(key),
                type=ptype,
                required=bool(spec.get("required", "default" not in spec)),
                default=spec.get("default"),
                description=str(spec.get("description", "")),
                secret=bool(spec.get("secret", False)),
            )
        )
    return params


def _parse_step(recipe: str, index: int, raw: Any) -> Step:
    where = f"recipe {recipe!r} step {index + 1}"
    if isinstance(raw, str):  # bare verb, no arguments: `- launch`
        raw = {raw: None}
    if not isinstance(raw, dict):
        raise RecipeError(f"{where}: each step must be a mapping like `- tap: {{text: OK}}`")

    meta = {k: v for k, v in raw.items() if k in STEP_META}
    verbs = [k for k in raw if k not in STEP_META]
    if len(verbs) != 1:
        raise RecipeError(
            f"{where}: expected exactly one verb, found {verbs or 'none'}. "
            "Write each action as its own list item."
        )
    verb = verbs[0]
    if verb not in VERBS:
        raise RecipeError(f"{where}: unknown step {verb!r}. Known steps: {sorted(VERBS)}")

    args = raw[verb]
    if args is None:
        args = {}
    elif not isinstance(args, dict):
        key = SCALAR_ARG.get(verb)
        if key is None:
            raise RecipeError(f"{where}: `{verb}` needs a mapping of arguments, got {args!r}")
        args = {key: args}
    else:
        # `retry` reads naturally beside `timeout_s`, so accept step options written
        # inside the verb's own mapping as well as beside it. Silently passing them
        # through as verb arguments instead fails at runtime with a confusing
        # signature error, and — worse — quietly drops the retry the author asked
        # for. No verb takes an argument by any of these names.
        args = dict(args)
        for key in sorted(STEP_META & set(args)):
            meta.setdefault(key, args.pop(key))

    return Step(
        verb=verb,
        args=args,
        retry=int(meta.get("retry", 0)),
        optional=bool(meta.get("optional", False)),
        settle_s=float(meta.get("settle_s", 0.0)),
        label=str(meta.get("label", "")),
    )


def parse(name: str, raw: Any) -> Recipe:
    """Turn one entry of the config's `recipes:` mapping into a Recipe."""
    if not NAME_RE.match(name):
        raise RecipeError(f"recipe name {name!r} must match {NAME_RE.pattern} to be usable as a tool name")
    if isinstance(raw, list):  # shorthand: just steps
        raw = {"steps": raw}
    if not isinstance(raw, dict):
        raise RecipeError(f"recipe {name!r} must be a mapping, got {type(raw).__name__}")

    unknown = set(raw) - {"description", "params", "steps", "on_failure"}
    if unknown:
        raise RecipeError(f"recipe {name!r}: unknown key(s) {sorted(unknown)}")

    steps_raw = raw.get("steps")
    if not steps_raw:
        raise RecipeError(f"recipe {name!r} has no steps")
    if not isinstance(steps_raw, list):
        raise RecipeError(f"recipe {name!r}: `steps` must be a list")

    on_failure = str(raw.get("on_failure", "stop"))
    if on_failure not in {"stop", "continue"}:
        raise RecipeError(f"recipe {name!r}: on_failure must be 'stop' or 'continue', got {on_failure!r}")

    return Recipe(
        name=name,
        description=str(raw.get("description", "") or f"Run the {name} flow"),
        params=_parse_params(name, raw.get("params")),
        steps=[_parse_step(name, i, s) for i, s in enumerate(steps_raw)],
        on_failure=on_failure,
    )


def load_all(cfg: Config) -> dict[str, Recipe]:
    """Parse every recipe in the config. One bad recipe does not hide the others."""
    out: dict[str, Recipe] = {}
    for name, raw in (cfg.recipes or {}).items():
        try:
            out[str(name)] = parse(str(name), raw)
        except RecipeError as e:
            log("recipes", f"SKIPPED: {e}")
    return out


# ── interpolation ─────────────────────────────────────────────────────────────


def interpolate(value: Any, params: dict[str, Any]) -> Any:
    """Substitute `{{param}}` throughout a step's arguments.

    A value that is *entirely* one placeholder keeps the parameter's own type, so
    `timeout_s: "{{wait}}"` with `wait=30` stays the integer 30 rather than "30".
    """
    if isinstance(value, str):
        whole = WHOLE_PLACEHOLDER_RE.match(value.strip())
        if whole:
            return _lookup(whole.group(1), params)
        return PLACEHOLDER_RE.sub(lambda m: str(_lookup(m.group(1), params)), value)
    if isinstance(value, dict):
        return {k: interpolate(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v, params) for v in value]
    return value


def _lookup(name: str, params: dict[str, Any]) -> Any:
    if name not in params:
        raise StepFailed(
            f"{{{{{name}}}}} is not a parameter of this recipe. Available: {sorted(params) or '(none)'}"
        )
    return params[name]


# ── execution ─────────────────────────────────────────────────────────────────


class Context:
    """Everything a step needs to touch the device."""

    def __init__(self, session: Session, cfg: Config, runs: Runs) -> None:
        self.session = session
        self.cfg = cfg
        self.runs = runs


def _expect_result(result: dict[str, Any]) -> dict[str, Any]:
    """Turn a failed assertion into a step failure; pass a successful one through."""
    if result.get("ok") is False:
        raise StepFailed(str(result.get("error", "assertion failed")), result)
    return result


def _step_sleep(ctx: Context, seconds: float = 1.0) -> dict[str, Any]:
    time.sleep(float(seconds))
    return {"slept_s": float(seconds)}


def _step_screenshot(ctx: Context, name: str | None = None) -> dict[str, Any]:
    stem = name or f"step-{int(time.time() * 1000) % 100000}"
    path = ctx.runs.artifact_dir("screenshots") / f"{stem}.png"
    actions.screenshot(ctx.session, path)
    return {"screenshot": str(path)}


# verb → (callable taking (ctx, **args))
VERBS: dict[str, Callable[..., dict[str, Any]]] = {
    # UI
    "tap": lambda ctx, **kw: actions.tap(ctx.session, **_rename_id(kw)),
    "tap_xy": lambda ctx, **kw: actions.tap_xy(ctx.session, **kw),
    "long_press": lambda ctx, **kw: actions.long_press(ctx.session, **_rename_id(kw)),
    "type": lambda ctx, **kw: actions.type_text(ctx.session, **_rename_id(kw)),
    "swipe": lambda ctx, **kw: actions.swipe(ctx.session, **kw),
    "scroll_to": lambda ctx, **kw: actions.scroll_to(ctx.session, **_rename_id(kw)),
    "press": lambda ctx, **kw: actions.press_key(ctx.session, **kw),
    "screenshot": _step_screenshot,
    # app lifecycle
    "build": lambda ctx, **kw: actions.build_app(ctx.cfg, **kw),
    "install": lambda ctx, **kw: actions.install_app(ctx.session, ctx.cfg, **kw),
    "uninstall": lambda ctx, **kw: actions.uninstall_app(ctx.session, ctx.cfg, **kw),
    "launch": lambda ctx, **kw: actions.launch_app(ctx.session, ctx.cfg, **kw),
    "force_stop": lambda ctx, **kw: actions.force_stop(ctx.session, ctx.cfg, **kw),
    "clear_data": lambda ctx, **kw: actions.clear_app_data(ctx.session, ctx.cfg, **kw),
    # emulator
    "snapshot_save": lambda ctx, **kw: emulator.snapshot_save(ctx.session.serial, **kw),
    "snapshot_load": lambda ctx, **kw: _after_snapshot(ctx, emulator.snapshot_load(ctx.session.serial, **kw)),
    # assertions
    "expect_visible": lambda ctx, **kw: _expect_result(expect.visible(ctx.session, **_rename_id(kw))),
    "expect_gone": lambda ctx, **kw: _expect_result(expect.gone(ctx.session, **_rename_id(kw))),
    "expect_log": lambda ctx, **kw: _expect_result(expect.log_matches(ctx.session, ctx.cfg, **kw)),
    "expect_no_crash": lambda ctx, **kw: _expect_result(expect.no_crash(ctx.session, ctx.cfg, **kw)),
    # misc
    "sleep": _step_sleep,
    "shell": lambda ctx, **kw: actions.shell(ctx.session, **kw),
    "logcat_clear": lambda ctx: (adb.logcat_clear(ctx.session.serial), {})[1],
    "run": lambda ctx, **kw: {},  # replaced by Runner; declared here so parsing accepts it
}


def _rename_id(kw: dict[str, Any]) -> dict[str, Any]:
    """`id:` reads better in YAML than `rid:`, which is what the action layer takes."""
    if "id" in kw:
        kw = dict(kw)
        kw["rid"] = kw.pop("id")
    return kw


def _after_snapshot(ctx: Context, result: dict[str, Any]) -> dict[str, Any]:
    ctx.session.invalidate()
    return result


class Runner:
    def __init__(self, ctx: Context, registry: dict[str, Recipe]) -> None:
        self.ctx = ctx
        self.registry = registry

    def run(self, recipe: Recipe, params: dict[str, Any], depth: int = 0) -> dict[str, Any]:
        if depth > MAX_RECIPE_DEPTH:
            raise StepFailed(f"recipe nesting deeper than {MAX_RECIPE_DEPTH}; is {recipe.name!r} recursive?")

        bound = self._bind(recipe, params)
        redacted = {
            p.name: ("***" if p.secret else bound[p.name]) for p in recipe.params if p.name in bound
        }
        log("recipes", f"running {recipe.name}({redacted})")

        started = time.monotonic()
        records: list[dict[str, Any]] = []
        failure: dict[str, Any] | None = None

        for index, step in enumerate(recipe.steps):
            record = self._run_step(recipe, index, step, bound, depth)
            records.append(record)
            if record["status"] == "failed":
                failure = record
                if recipe.on_failure == "stop":
                    break

        ok = failure is None
        result: dict[str, Any] = {
            "ok": ok,
            "recipe": recipe.name,
            "params": redacted,
            "steps": records,
            "duration_s": round(time.monotonic() - started, 2),
        }
        if failure is not None:
            result["error"] = f"step {failure['index']} (`{failure['step']}`) failed: {failure['error']}"
            result["failed_step"] = failure
        return result

    # ── internals ────────────────────────────────────────────────────────────

    def _bind(self, recipe: Recipe, params: dict[str, Any]) -> dict[str, Any]:
        known = recipe.param_map
        unknown = set(params) - set(known)
        if unknown:
            raise StepFailed(
                f"recipe {recipe.name!r} got unknown parameter(s) {sorted(unknown)}; "
                f"it takes {sorted(known) or '(none)'}"
            )
        bound: dict[str, Any] = {}
        for param in recipe.params:
            if param.name in params and params[param.name] is not None:
                bound[param.name] = params[param.name]
            elif param.required:
                raise StepFailed(f"recipe {recipe.name!r} requires the {param.name!r} parameter")
            else:
                bound[param.name] = param.default
        return bound

    def _run_step(
        self, recipe: Recipe, index: int, step: Step, params: dict[str, Any], depth: int
    ) -> dict[str, Any]:
        label = f"{recipe.name}.{step.name}"
        started = time.monotonic()
        attempts = step.retry + 1
        last_error: Exception | None = None
        detail: dict[str, Any] = {}

        for attempt in range(attempts):
            try:
                args = interpolate(step.args, params)
                payload = self._dispatch(step.verb, args, depth) or {}
                if step.settle_s:
                    time.sleep(step.settle_s)
                duration = round(time.monotonic() - started, 3)
                self.ctx.runs.record_event(label, "ok", duration, summarize(payload))
                return {
                    "index": index + 1,
                    "step": step.name,
                    "status": "ok",
                    "duration_s": duration,
                    **summarize(payload),
                }
            except Exception as e:
                last_error = e
                detail = getattr(e, "detail", {}) or {}
                if attempt < attempts - 1:
                    log("recipes", f"{label} failed ({e}); retry {attempt + 1}/{step.retry}")
                    time.sleep(0.5 * (attempt + 1))
                    # Re-read the screen before trying again. A retry against the
                    # same cached snapshot can only fail the same way, and the
                    # usual reason a step needs retrying is that the UI had not
                    # finished settling when we looked.
                    self.ctx.session.invalidate()

        duration = round(time.monotonic() - started, 3)
        message = f"{type(last_error).__name__}: {last_error}"
        artifacts = self.ctx.runs.capture(self.ctx.session, f"{recipe.name}-{index + 1}-{step.verb}")
        status = "skipped" if step.optional else "failed"
        record = {
            "index": index + 1,
            "step": step.name,
            "status": status,
            "duration_s": duration,
            "error": message,
            **artifacts,
        }
        if detail.get("screen"):
            record["screen"] = detail["screen"]
        self.ctx.runs.record_event(label, status, duration, {"error": message, **artifacts})
        return record

    def _dispatch(self, verb: str, args: dict[str, Any], depth: int) -> dict[str, Any]:
        if verb == "run":
            nested = args.get("recipe")
            if nested not in self.registry:
                raise StepFailed(f"no recipe named {nested!r}. Known: {sorted(self.registry)}")
            child_params = {k: v for k, v in args.items() if k != "recipe"}
            result = self.run(self.registry[nested], child_params, depth + 1)
            if not result["ok"]:
                raise StepFailed(result.get("error", f"nested recipe {nested!r} failed"), result)
            return {"recipe": nested, "steps": len(result["steps"])}
        try:
            return VERBS[verb](self.ctx, **args)
        except TypeError as e:
            # A wrong argument name is a config mistake, so say so in those terms
            # rather than leaking a Python signature error at the agent.
            raise StepFailed(f"`{verb}` does not accept those arguments ({e})") from e


def summarize(payload: dict[str, Any], limit: int = 300) -> dict[str, Any]:
    """Keep timeline entries readable — drop the bulky fields assertions return."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"screen", "excerpt", "tail", "matches", "steps"}:
            continue
        if isinstance(value, str) and len(value) > limit:
            value = value[:limit] + "…"
        out[key] = value
    return out


# ── MCP tool generation ───────────────────────────────────────────────────────


def build_tool(recipe: Recipe, runner_factory: Callable[[], Runner]) -> Callable[..., dict[str, Any]]:
    """Wrap a recipe in a function whose signature is its parameter list.

    FastMCP derives a tool's JSON schema from `inspect.signature`, so a synthetic
    signature is what makes `login(email, password)` show up as a typed tool
    instead of an opaque `run_recipe(name, params)` call.
    """
    def tool(**kwargs: Any) -> dict[str, Any]:
        try:
            return runner_factory().run(recipe, kwargs)
        except StepFailed as e:
            return {"ok": False, "recipe": recipe.name, "error": str(e), **(e.detail or {})}
        except Exception as e:
            return {"ok": False, "recipe": recipe.name, "error": f"{type(e).__name__}: {e}"}

    ordered = sorted(recipe.params, key=lambda p: not p.required)
    parameters = [
        inspect.Parameter(
            p.name,
            inspect.Parameter.KEYWORD_ONLY,
            default=inspect.Parameter.empty if p.required else p.default,
            annotation=p.py_type if p.required else (p.py_type | None),
        )
        for p in ordered
    ]
    tool.__signature__ = inspect.Signature(parameters, return_annotation=dict[str, Any])  # type: ignore[attr-defined]
    tool.__name__ = recipe.name
    tool.__doc__ = _docstring(recipe)
    return tool


def _docstring(recipe: Recipe) -> str:
    lines = [recipe.description.strip() or f"Run the {recipe.name} flow."]
    if recipe.params:
        lines.append("")
        for p in recipe.params:
            suffix = "" if p.required else f" (default: {p.default!r})"
            lines.append(f"  {p.name}: {p.description or p.type}{suffix}")
    lines.append("")
    lines.append(f"Steps: {' → '.join(s.name for s in recipe.steps)}")
    return "\n".join(lines)
