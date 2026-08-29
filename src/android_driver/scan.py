"""Selector scanning — what names actually exist in the app under test.

A recipe written against `desc: login_buton` fails at step four with "element not
found", and the agent then spends three tool calls proving the typo. Scanning the
project's own sources for the literals it declares turns that into a load-time
warning, and gives an agent a list of real names to write recipes against in the
first place.

The default patterns cover the two things Android apps actually label elements
with — Compose `testTag`/`contentDescription` and View-system `android:id` — plus
string resources, since visible copy is what `text:` selectors match. Projects
with their own convention add regexes under `selectors.patterns`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .log import log

# Default globs, tried when the config does not name any.
DEFAULT_SOURCES = (
    "**/src/**/*.kt",
    "**/src/**/*.java",
    "**/src/main/res/layout*/*.xml",
    "**/src/main/res/values/strings.xml",
)

# Directories never worth walking — build outputs dwarf the sources.
SKIP_DIRS = {"build", ".git", ".gradle", ".idea", "node_modules", "venv", ".venv", "__pycache__"}

# kind → regex with one capturing group holding the literal.
PATTERNS: dict[str, re.Pattern[str]] = {
    # testTag("x"), testSemanticsTag("x"), fooTestTag = "x"
    "tag": re.compile(r'[A-Za-z_]*[Tt]est(?:Semantics)?[Tt]ag\b\s*[=(]\s*"([^"\n]+)"'),
    # contentDescription = "x" / contentDescription("x")
    "desc": re.compile(r'contentDescription\s*[=(]\s*"([^"\n]+)"'),
    # android:id="@+id/x" and R.id.x
    "id": re.compile(r'android:id\s*=\s*"@\+?id/([\w.]+)"'),
    "id_ref": re.compile(r"\bR\.id\.(\w+)"),
    # <string name="x">visible copy</string>
    "text": re.compile(r'<string\s+name="[^"]+"\s*>([^<]{1,80})</string>'),
}

# Literals that resolve at runtime (`testTag = "demo_${item.name}_button"`) can
# never match a live element as written, so they are reported separately rather
# than presented as names a recipe can use.
TEMPLATE_RE = re.compile(r"\$\{|\$[A-Za-z_]|%[sd]|\{\d*\}")


@dataclass
class Selectors:
    by_kind: dict[str, set[str]]
    templates: set[str]
    files_scanned: int

    @property
    def all(self) -> set[str]:
        return {value for values in self.by_kind.values() for value in values}

    def to_dict(self, limit: int | None = None) -> dict[str, list[str]]:
        out = {kind: sorted(values) for kind, values in sorted(self.by_kind.items()) if values}
        if limit:
            out = {kind: values[:limit] for kind, values in out.items()}
        return out


def _iter_files(root: Path, globs: list[str]) -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in globs:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            seen[path] = None
    return list(seen)


def scan(cfg: Config) -> Selectors:
    """Collect every selector literal the project declares."""
    spec = cfg.selectors or {}
    globs = list(spec.get("sources") or DEFAULT_SOURCES)
    extra = spec.get("patterns") or []

    patterns = dict(PATTERNS)
    for i, raw in enumerate(extra):
        try:
            patterns[f"custom{i + 1}"] = re.compile(raw)
        except re.error as e:
            log("scan", f"ignoring selectors.patterns[{i}] {raw!r}: {e}")

    by_kind: dict[str, set[str]] = {kind: set() for kind in patterns}
    templates: set[str] = set()
    files = _iter_files(cfg.project_root, globs)

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            log("scan", f"could not read {path}: {e}")
            continue
        for kind, rx in patterns.items():
            for match in rx.finditer(text):
                literal = (match.group(1) if rx.groups else match.group(0)).strip()
                if not literal:
                    continue
                if TEMPLATE_RE.search(literal):
                    templates.add(literal)
                else:
                    by_kind[kind].add(literal)

    # id and id_ref are the same namespace seen from XML and from Kotlin.
    by_kind["id"] |= by_kind.pop("id_ref", set())
    log("scan", f"scanned {len(files)} file(s); found {sum(len(v) for v in by_kind.values())} selectors")
    return Selectors(by_kind=by_kind, templates=templates, files_scanned=len(files))


def check_recipes(recipes: dict, known: Selectors) -> list[str]:
    """Warn about recipe selectors the project's sources do not declare.

    Only `desc` and `id` are checked. `text` selectors match visible copy that may
    come from a translation, a server response or a formatted string, so absence
    from the scanned set means nothing — flagging it would produce noise an
    operator learns to ignore, which is worse than not checking.
    """
    if not known.all:
        return []
    warnings: list[str] = []
    tags = known.by_kind.get("tag", set()) | known.by_kind.get("desc", set())
    ids = known.by_kind.get("id", set())
    for name, recipe in recipes.items():
        for index, step in enumerate(recipe.steps, start=1):
            for key, pool, label in (("desc", tags, "testTag/contentDescription"), ("id", ids, "id")):
                value = step.args.get(key) if isinstance(step.args, dict) else None
                if not isinstance(value, str) or "{{" in value or not pool:
                    continue
                if value not in pool:
                    near = _closest(value, pool)
                    hint = f" Did you mean {near!r}?" if near else ""
                    warnings.append(
                        f"{name} step {index} (`{step.verb}`) uses {key}={value!r}, "
                        f"which is not among the project's {label} literals.{hint}"
                    )
    return warnings


def _closest(value: str, pool: set[str]) -> str | None:
    import difflib

    matches = difflib.get_close_matches(value, pool, n=1, cutoff=0.75)
    return matches[0] if matches else None
