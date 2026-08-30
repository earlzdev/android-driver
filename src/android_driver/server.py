"""MCP entrypoint. Thin registrations only — the logic lives in the modules below.

Return-shape convention:
  * action tools return `{"ok": bool, "error"?: str, ...}` so an agent can branch
    without exception handling;
  * assertions add `"passed"`, which mirrors `ok`;
  * read tools (`screen`, `logcat_read`, `dump_ui_xml`) return their natural type.

Every device-touching failure captures a screenshot and a hierarchy dump on its
way out, into the open run's directory or `runs/failures/` — evidence you did not
have to think to collect is the only kind that survives a long agent session.

stdout belongs to the JSON-RPC frame. Every diagnostic goes to stderr via `log`.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from . import actions, adb, emulator, expect, scan, ui
from . import config as config_mod
from . import recipes as recipes_mod
from .log import log
from .record import Recorder
from .run import Runs
from .session import Session

mcp = FastMCP("android-driver")

CFG = config_mod.load()
SESSION = Session(CFG)
RUNS = Runs(CFG)
RECORDER = Recorder()
RECIPES: dict[str, recipes_mod.Recipe] = {}
_SELECTORS: scan.Selectors | None = None
# Names this server registered for recipes, so `reload_config` can retire them.
_RECIPE_TOOLS: list[str] = []


def _ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, **fields}


def _err(exc: BaseException) -> dict[str, Any]:
    return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _act(tool: str, fn, *, artifacts: bool = False) -> dict[str, Any]:
    """Run one action: time it, record it on the open run, capture evidence if it fails."""
    started = time.monotonic()
    try:
        payload = fn()
        payload = payload if isinstance(payload, dict) else ({} if payload is None else {"result": payload})
        if payload.get("ok") is False:  # an assertion that legitimately failed
            evidence = RUNS.capture(SESSION, tool) if artifacts else {}
            payload = {**payload, **evidence}
            RUNS.record_event(tool, "failed", time.monotonic() - started, recipes_mod.summarize(payload))
            return payload
        payload.pop("ok", None)
        RUNS.record_event(tool, "ok", time.monotonic() - started, recipes_mod.summarize(payload))
        return _ok(**payload)
    except Exception as e:
        duration = time.monotonic() - started
        evidence = RUNS.capture(SESSION, tool) if artifacts else {}
        RUNS.record_event(tool, "failed", duration, {"error": f"{type(e).__name__}: {e}", **evidence})
        return {**_err(e), **evidence}


def _runner() -> recipes_mod.Runner:
    return recipes_mod.Runner(recipes_mod.Context(SESSION, CFG, RUNS), RECIPES)


def _selectors(refresh: bool = False) -> scan.Selectors:
    global _SELECTORS
    if _SELECTORS is None or refresh:
        _SELECTORS = scan.scan(CFG)
    return _SELECTORS


# ── emulator lifecycle ────────────────────────────────────────────────────────


@mcp.tool()
def list_avds() -> dict[str, Any]:
    """List every Android Virtual Device configured on this machine."""
    return _act("list_avds", lambda: {"avds": emulator.list_avds(), "running": emulator.running_emulators()})


@mcp.tool()
def start_emulator(
    avd: str,
    headless: bool = False,
    cold_boot: bool = False,
    wipe_data: bool = False,
    snapshot: str | None = None,
) -> dict[str, Any]:
    """Boot an AVD and wait until it is fully usable, then select it for this session.

    Returns the emulator's serial. If the AVD is already running, reuses it.
    `cold_boot` skips the saved quick-boot state; `wipe_data` factory-resets first.
    """

    def run() -> dict[str, Any]:
        result = emulator.start(
            avd,
            headless=headless,
            cold_boot=cold_boot,
            wipe_data=wipe_data,
            snapshot=snapshot,
            boot_timeout_s=CFG.timing.boot_timeout_s,
        )
        if result.get("ok") and result.get("serial"):
            SESSION.select(result["serial"])
        return result

    return _act("start_emulator", run)


@mcp.tool()
def stop_emulator(serial: str | None = None) -> dict[str, Any]:
    """Shut down a running emulator (defaults to the selected device)."""
    return _act("stop_emulator", lambda: emulator.stop(serial or SESSION.serial))


@mcp.tool()
def wait_for_boot(serial: str | None = None, timeout_s: int | None = None) -> dict[str, Any]:
    """Block until the device finishes booting (framework up and boot animation done)."""
    return _act(
        "wait_for_boot",
        lambda: emulator.wait_for_boot(serial or SESSION.serial, timeout_s or CFG.timing.boot_timeout_s),
    )


@mcp.tool()
def snapshot_save(name: str) -> dict[str, Any]:
    """Freeze the emulator's exact current state under `name`.

    Save one right after the app is installed and sitting on the screen your test
    starts from. Restoring it later is 10-30x faster than reinstalling and
    re-navigating, and it is byte-identical every time — which is what makes an
    intermittent bug reproducible.
    """
    return _act("snapshot_save", lambda: emulator.snapshot_save(SESSION.serial, name))


@mcp.tool()
def snapshot_load(name: str) -> dict[str, Any]:
    """Restore the emulator to a previously saved snapshot."""

    def run() -> dict[str, Any]:
        result = emulator.snapshot_load(SESSION.serial, name)
        SESSION.invalidate()
        return result

    return _act("snapshot_load", run)


@mcp.tool()
def snapshot_list() -> dict[str, Any]:
    """List snapshots saved for the running emulator."""
    return _act("snapshot_list", lambda: {"snapshots": emulator.snapshot_list(SESSION.serial)})


@mcp.tool()
def snapshot_delete(name: str) -> dict[str, Any]:
    """Delete a saved snapshot."""
    return _act("snapshot_delete", lambda: emulator.snapshot_delete(SESSION.serial, name))


# ── device ────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_devices() -> dict[str, Any]:
    """List attached devices and emulators in state `device`."""
    return _act("list_devices", lambda: {"devices": adb.list_devices(), "selected": SESSION.current_serial})


@mcp.tool()
def select_device(serial: str) -> dict[str, Any]:
    """Pin a device for the rest of this session."""
    return _act("select_device", lambda: (SESSION.select(serial), {"serial": serial})[1])


@mcp.tool()
def device_info() -> dict[str, Any]:
    """Model, Android version, ABI, screen size and density of the selected device."""
    return _act("device_info", lambda: adb.device_info(SESSION.serial))


# ── app lifecycle ─────────────────────────────────────────────────────────────


@mcp.tool()
def build_app() -> dict[str, Any]:
    """Run the project's configured build command and return the APK it produced."""
    return _act("build_app", lambda: actions.build_app(CFG))


@mcp.tool()
def install_app(
    apk_path: str | None = None, build_first: bool = False, pkg: str | None = None
) -> dict[str, Any]:
    """Install the app: force-stop, uninstall, install, grant runtime permissions, verify.

    Uninstall-then-install is the default because debug APKs from different
    branches carry different signing keys, and reinstalling over one with the
    other fails with INSTALL_FAILED_UPDATE_INCOMPATIBLE.

    `pkg` overrides the configured package, so an explicit APK can be installed
    with no project config at all.
    """
    return _act("install_app", lambda: actions.install_app(SESSION, CFG, apk_path, build_first, pkg))


@mcp.tool()
def uninstall_app(pkg: str | None = None) -> dict[str, Any]:
    """Uninstall a package (defaults to the configured app)."""
    return _act("uninstall_app", lambda: actions.uninstall_app(SESSION, CFG, pkg))


@mcp.tool()
def app_info(pkg: str | None = None) -> dict[str, Any]:
    """Whether the app is installed, and its version metadata."""
    return _act("app_info", lambda: adb.app_info(SESSION.serial, pkg or CFG.package))


@mcp.tool()
def launch_app(pkg: str | None = None, cold: bool = True) -> dict[str, Any]:
    """Start the app and wait out cold-start rendering.

    `cold=True` force-stops first, so the app really starts from scratch rather
    than resuming whatever screen it was left on.
    """
    return _act("launch_app", lambda: actions.launch_app(SESSION, CFG, pkg, cold), artifacts=True)


@mcp.tool()
def force_stop(pkg: str | None = None) -> dict[str, Any]:
    """Kill every process of the app."""
    return _act("force_stop", lambda: actions.force_stop(SESSION, CFG, pkg))


@mcp.tool()
def clear_app_data(pkg: str | None = None) -> dict[str, Any]:
    """Wipe the app's data and cache, returning it to first-launch state."""
    return _act("clear_app_data", lambda: actions.clear_app_data(SESSION, CFG, pkg))


# ── UI ────────────────────────────────────────────────────────────────────────


@mcp.tool()
def screen() -> str:
    """Read the current screen as a compact list of interactive and readable elements.

    Each line carries a `#N` reference you can pass straight to `tap`:

        #1 [Button] "Sign in" desc=login_button @(540,1320)
        #2 [EditText] "" hint="Email" @(540,980)

    Call this before interacting with an unfamiliar screen. For the raw
    accessibility tree, use `dump_ui_xml` — but it is very large, so prefer this.
    """
    try:
        return ui.render(SESSION.refresh(), header=SESSION.header())
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


@mcp.tool()
def tap(
    ref: str | None = None,
    text: str | None = None,
    contains: str | None = None,
    desc: str | None = None,
    id: str | None = None,
    index: int = 0,
) -> dict[str, Any]:
    """Tap an element. Give exactly one selector.

    `ref` is a `#N` from `screen`. `text` and `desc` match exactly; `contains`
    matches a substring of either, case-insensitively. `index` picks among
    multiple matches.
    """
    return _act(
        "tap",
        lambda: actions.tap(SESSION, ref=ref, text=text, contains=contains, desc=desc, rid=id, index=index),
        artifacts=True,
    )


@mcp.tool()
def tap_xy(x: int, y: int) -> dict[str, Any]:
    """Tap raw device coordinates. Prefer `tap` with a selector where possible."""
    return _act("tap_xy", lambda: actions.tap_xy(SESSION, x, y), artifacts=True)


@mcp.tool()
def long_press(
    ref: str | None = None,
    text: str | None = None,
    contains: str | None = None,
    desc: str | None = None,
    id: str | None = None,
    duration_s: float = 1.0,
    index: int = 0,
) -> dict[str, Any]:
    """Press and hold an element — context menus, drag handles, multi-select."""
    return _act(
        "long_press",
        lambda: actions.long_press(
            SESSION, ref=ref, text=text, contains=contains, desc=desc, rid=id,
            duration_s=duration_s, index=index,
        ),
        artifacts=True,
    )


@mcp.tool()
def type_text(
    text: str,
    ref: str | None = None,
    desc: str | None = None,
    id: str | None = None,
    contains: str | None = None,
    index: int = 0,
) -> dict[str, Any]:
    """Replace a text field's contents with `text`, then close the keyboard.

    Targets the field directly rather than tapping and typing, which is the only
    reliable approach on Jetpack Compose — a tap does not always move focus and
    the text can land in the wrong field.
    """
    return _act(
        "type_text",
        lambda: actions.type_text(SESSION, text, ref=ref, desc=desc, rid=id, contains=contains, index=index),
        artifacts=True,
    )


@mcp.tool()
def swipe(direction: str = "up", distance: float = 0.6, duration_s: float = 0.3) -> dict[str, Any]:
    """Swipe across the middle of the screen. `direction`: up, down, left, right.

    `up` scrolls content downward (the usual "show me more"). `distance` is a
    fraction of the screen.
    """
    return _act("swipe", lambda: actions.swipe(SESSION, direction, distance, duration_s))


@mcp.tool()
def scroll_to(
    text: str | None = None,
    contains: str | None = None,
    desc: str | None = None,
    id: str | None = None,
    direction: str = "up",
    max_swipes: int = 8,
) -> dict[str, Any]:
    """Swipe until an element comes into view, then stop.

    Works on both backends — it is a swipe loop, not a driver feature — so a
    target below the fold does not need coordinates worked out by hand.
    """
    return _act(
        "scroll_to",
        lambda: actions.scroll_to(
            SESSION, text=text, contains=contains, desc=desc, rid=id,
            direction=direction, max_swipes=max_swipes,
        ),
        artifacts=True,
    )


@mcp.tool()
def press_key(key: str) -> dict[str, Any]:
    """Send a hardware key: back, home, enter, recent, volume_up, delete, or a raw KEYCODE_*."""
    return _act("press_key", lambda: actions.press_key(SESSION, key))


@mcp.tool()
def screenshot(name: str | None = None) -> Image:
    """Capture the screen as a PNG. Use `screen` first — it is far cheaper for finding elements.

    Inside an open run the file lands in that run's directory, so it ends up in
    the report without any extra bookkeeping.
    """
    stem = name or f"screen-{int(time.time() * 1000) % 100000}"
    path = RUNS.artifact_dir("screenshots") / f"{stem}.png"
    actions.screenshot(SESSION, path)
    RUNS.record_event("screenshot", "ok", 0.0, {"screenshot": str(path)})
    return Image(path=str(path), format="png")


@mcp.tool()
def dump_ui_xml() -> str:
    """The raw accessibility hierarchy XML.

    Large (tens of thousands of tokens on a busy screen). Use `screen` unless you
    specifically need attributes it does not surface.
    """
    try:
        return SESSION.driver.dump_hierarchy()
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


# ── assertions ────────────────────────────────────────────────────────────────


@mcp.tool()
def expect_visible(
    text: str | None = None,
    contains: str | None = None,
    desc: str | None = None,
    id: str | None = None,
    cls: str | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Assert an element appears within `timeout_s`. Polls, so it is safe right after a tap.

    On failure the result carries the screen index that *was* there, so you can
    see what the app actually showed without another call.
    """
    return _act(
        "expect_visible",
        lambda: expect.visible(
            SESSION, timeout_s, text=text, contains=contains, desc=desc, rid=id, cls=cls
        ),
        artifacts=True,
    )


@mcp.tool()
def expect_gone(
    text: str | None = None,
    contains: str | None = None,
    desc: str | None = None,
    id: str | None = None,
    cls: str | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Assert an element disappears within `timeout_s` — dialogs, spinners, toasts."""
    return _act(
        "expect_gone",
        lambda: expect.gone(SESSION, timeout_s, text=text, contains=contains, desc=desc, rid=id, cls=cls),
        artifacts=True,
    )


@mcp.tool()
def expect_log(
    pattern: str,
    timeout_s: float = 30.0,
    only_app: bool = True,
    level: str | None = None,
) -> dict[str, Any]:
    """Assert a logcat line matching the regex `pattern` shows up within `timeout_s`.

    Clear the buffer first (`logcat_clear`, or open a run) — otherwise a match
    left over from an earlier attempt passes this trivially.
    """
    return _act(
        "expect_log",
        lambda: expect.log_matches(SESSION, CFG, pattern, timeout_s, only_app=only_app, level=level),
    )


@mcp.tool()
def expect_no_crash(pkg: str | None = None, lines: int = 4000) -> dict[str, Any]:
    """Assert the app did not crash: no fatal exception, ANR, native abort or tombstone.

    Reads the `crash` buffer as well as `main`, because a native abort never
    reaches `main` at all.
    """
    return _act("expect_no_crash", lambda: expect.no_crash(SESSION, CFG, pkg, lines))


# ── runs ──────────────────────────────────────────────────────────────────────


@mcp.tool()
def run_start(name: str, note: str = "", clear_log: bool = True) -> dict[str, Any]:
    """Open a run: from here every action is timed and recorded, and failures save evidence.

    Clears logcat by default so the run's log slice covers exactly this attempt.
    Close it with `run_end`, which writes `report.md` and `timeline.json`.
    """
    return _act("run_start", lambda: RUNS.start(SESSION, name, note, clear_log))


@mcp.tool()
def run_end() -> dict[str, Any]:
    """Close the open run: write the logcat slice, timeline and report; return the verdict."""
    return _act("run_end", lambda: RUNS.end(SESSION))


@mcp.tool()
def run_list(limit: int = 20) -> dict[str, Any]:
    """List previous runs, newest first, with their pass/fail verdict."""
    return _act("run_list", lambda: {"runs": RUNS.list_runs(limit)})


@mcp.tool()
def record_start(
    name: str | None = None,
    bit_rate_mbps: float = 4.0,
    size: str | None = None,
    time_limit_s: int = 180,
) -> dict[str, Any]:
    """Start recording the screen. `screenrecord` caps a clip at 180 seconds."""
    return _act(
        "record_start",
        lambda: RECORDER.start(
            SESSION.serial, name=name, bit_rate_mbps=bit_rate_mbps, size=size, time_limit_s=time_limit_s
        ),
    )


@mcp.tool()
def record_stop(name: str | None = None) -> dict[str, Any]:
    """Stop recording and pull the MP4 into the open run's directory (or `runs/`)."""

    def run() -> dict[str, Any]:
        stem = name or "recording"
        dest = RUNS.artifact_dir("recordings") / f"{stem}.mp4"
        result = RECORDER.stop(dest)
        if RUNS.current is not None:
            RUNS.current.recording = result
        return result

    return _act("record_stop", run)


# ── recipes and selectors ─────────────────────────────────────────────────────


@mcp.tool()
def list_recipes() -> dict[str, Any]:
    """The project's configured flows, with their parameters and steps."""
    return _ok(
        recipes=[
            {
                "name": r.name,
                "description": r.description,
                "params": [
                    {"name": p.name, "type": p.type, "required": p.required, "default": p.default}
                    for p in r.params
                ],
                "steps": [s.name for s in r.steps],
            }
            for r in RECIPES.values()
        ]
    )


@mcp.tool()
def run_recipe(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a configured flow by name.

    Each recipe is also registered as its own tool with typed parameters; this is
    the generic escape hatch for building a call programmatically.
    """

    def run() -> dict[str, Any]:
        if name not in RECIPES:
            raise KeyError(f"no recipe named {name!r}. Known: {sorted(RECIPES) or '(none configured)'}")
        return _runner().run(RECIPES[name], params or {})

    return _act(f"recipe:{name}", run)


@mcp.tool()
def reload_config() -> dict[str, Any]:
    """Re-read the project config and recipes without restarting the server.

    The config is read once at startup, so editing `.android-driver.yaml` — or
    creating one — otherwise needs an MCP reconnect before anything picks it up.
    Recipe tools are re-registered here, but most clients cache the tool list, so
    a recipe you have just *added* may still need a client-side refresh to appear.
    The selected device is preserved.
    """

    def run() -> dict[str, Any]:
        global CFG, SESSION, RUNS, _SELECTORS
        if RUNS.current is not None and not RUNS.current.finished:
            raise RuntimeError(
                f"run {RUNS.current.id!r} is still open; call `run_end` before reloading"
            )
        serial = SESSION.current_serial
        CFG = config_mod.load()
        SESSION = Session(CFG)
        if serial:
            try:
                SESSION.select(serial)
            except Exception as e:
                log("config", f"could not re-select {serial}: {e}")
        RUNS = Runs(CFG)
        _SELECTORS = None
        return {
            "config": str(CFG.source) if CFG.source else "defaults (no config file found)",
            "package": CFG.app.package,
            "recipe_tools": register_recipes(),
            "device": SESSION.current_serial,
        }

    return _act("reload_config", run)


@mcp.tool()
def list_selectors(kind: str | None = None, contains: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Selector literals declared in the project's own sources.

    Scans for `testTag` / `contentDescription` / `android:id` / string resources
    so you can write a recipe against a name that exists instead of guessing one.
    `kind` filters to tag, desc, id or text.
    """

    def run() -> dict[str, Any]:
        found = _selectors()
        data = found.to_dict()
        if kind:
            data = {k: v for k, v in data.items() if k == kind}
        if contains:
            needle = contains.lower()
            data = {k: [s for s in v if needle in s.lower()] for k, v in data.items()}
        return {
            "files_scanned": found.files_scanned,
            "selectors": {k: v[:limit] for k, v in data.items() if v},
            "runtime_templates": sorted(found.templates)[:limit],
        }

    return _act("list_selectors", run)


@mcp.tool()
def check_recipes() -> dict[str, Any]:
    """Cross-check every recipe's selectors against the project's sources.

    Catches the rename that would otherwise surface as "element not found" three
    steps into a flow.
    """

    def run() -> dict[str, Any]:
        warnings = scan.check_recipes(RECIPES, _selectors(refresh=True))
        return {"recipes": len(RECIPES), "warnings": warnings, "clean": not warnings}

    return _act("check_recipes", run)


# ── logs and shell ────────────────────────────────────────────────────────────


@mcp.tool()
def logcat_clear() -> dict[str, Any]:
    """Clear the log buffer. Call before an action you want a clean log for."""
    return _act("logcat_clear", lambda: (adb.logcat_clear(SESSION.serial), {})[1])


@mcp.tool()
def logcat_read(
    lines: int = 300,
    pattern: str | None = None,
    only_app: bool = True,
    level: str | None = None,
) -> str:
    """Read recent log lines. `pattern` is a regex; `level` is one of V D I W E F."""
    try:
        pkg = CFG.app.package if (only_app and CFG.app.package) else None
        found = adb.logcat_dump(SESSION.serial, lines=lines, pkg=pkg, pattern=pattern, level=level)
        return "\n".join(found) if found else "(no matching log lines)"
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


@mcp.tool()
def shell(cmd: str) -> dict[str, Any]:
    """Run an arbitrary `adb shell` command. Pipes and quoting work.

    Unrestricted by design: this is a development tool, not a sandbox. It can
    modify or wipe anything on the device.
    """
    return _act("shell", lambda: adb.shell_result(SESSION.serial, cmd))


# ── startup ───────────────────────────────────────────────────────────────────


RESERVED_TOOL_NAMES = (
    "list_avds", "start_emulator", "stop_emulator", "wait_for_boot",
    "snapshot_save", "snapshot_load", "snapshot_list", "snapshot_delete",
    "list_devices", "select_device", "device_info",
    "build_app", "install_app", "uninstall_app", "app_info", "launch_app",
    "force_stop", "clear_app_data",
    "screen", "tap", "tap_xy", "long_press", "type_text", "swipe", "scroll_to",
    "press_key", "screenshot", "dump_ui_xml",
    "expect_visible", "expect_gone", "expect_log", "expect_no_crash",
    "run_start", "run_end", "run_list", "record_start", "record_stop",
    "list_recipes", "run_recipe", "list_selectors", "check_recipes", "reload_config",
    "logcat_clear", "logcat_read", "shell",
)


def register_recipes() -> list[str]:
    """Register each configured recipe as its own MCP tool with typed parameters.

    Existing recipe tools are retired first. FastMCP's `add_tool` returns the
    *existing* tool when a name is already taken rather than replacing it, so
    without this a reload would leave every recipe frozen at the definition the
    server started with — the exact thing a reload is supposed to fix.
    """
    global RECIPES
    for name in _RECIPE_TOOLS:
        try:
            mcp._tool_manager.remove_tool(name)  # no public API for this yet
        except Exception as e:
            log("recipes", f"could not retire the old {name!r} tool: {e}")
    _RECIPE_TOOLS.clear()
    RECIPES = recipes_mod.load_all(CFG)
    reserved = set(RESERVED_TOOL_NAMES)
    registered: list[str] = []
    for name, recipe in RECIPES.items():
        tool_name = name if name not in reserved else f"recipe_{name}"
        try:
            mcp.add_tool(recipes_mod.build_tool(recipe, _runner), name=tool_name)
        except Exception as e:
            log("recipes", f"could not register {name!r} as a tool: {e}")
            continue
        reserved.add(tool_name)
        registered.append(tool_name)
        _RECIPE_TOOLS.append(tool_name)
    if registered:
        log("recipes", f"registered {len(registered)} recipe tool(s): {', '.join(registered)}")
    return registered


def _warn_about_drift() -> None:
    """Scan sources for selector drift in the background — never block startup on it."""
    try:
        for warning in scan.check_recipes(RECIPES, _selectors()):
            log("recipes", f"WARNING: {warning}")
    except Exception as e:
        log("recipes", f"selector check skipped: {e}")


def main() -> None:
    log("server", f"android_driver starting (config={CFG.source or 'defaults'})")
    register_recipes()
    if RECIPES:
        threading.Thread(target=_warn_about_drift, daemon=True).start()
    mcp.run()


if __name__ == "__main__":
    main()
