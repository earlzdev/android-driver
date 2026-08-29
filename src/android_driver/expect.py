"""Assertions — the verbs that turn *driving* an app into *testing* it.

Everything here returns `{"ok": bool, "passed": bool, ...}`. `ok` mirrors
`passed`, so an agent can branch on the same field it uses everywhere else, and
a failing assertion is a normal result rather than an exception.

Every failure carries enough context to act on without a follow-up call: a
missing element comes back with the screen index that *was* there, a log
assertion with the tail it searched. That is deliberate — the round trip an
agent would otherwise make is the expensive part.
"""

from __future__ import annotations

import re
import time
from typing import Any

from . import adb
from .config import Config
from .session import Session

# Patterns that mean "the app died", in the order we report them.
CRASH_PATTERNS = (
    ("fatal_exception", re.compile(r"FATAL EXCEPTION")),
    ("anr", re.compile(r"\bANR in ([\w.]+)")),
    ("native_crash", re.compile(r"signal \d+ \(SIG\w+\)")),
    ("tombstone", re.compile(r"Tombstone written to:")),
)

# How many lines around a crash marker we keep as the excerpt. The lookback
# matters for native crashes: `signal 11 (SIGSEGV)` says nothing about which
# process died — the `pid: ..., name: <pkg>` line above it does.
CRASH_CONTEXT_LINES = 25
CRASH_LOOKBACK_LINES = 6


def _active(selector: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in selector.items() if v is not None and k != "index"}


def _fail(reason: str, **fields: Any) -> dict[str, Any]:
    return {"ok": False, "passed": False, "error": reason, **fields}


def _pass(**fields: Any) -> dict[str, Any]:
    return {"ok": True, "passed": True, **fields}


def visible(session: Session, timeout_s: float = 10.0, **selector: Any) -> dict[str, Any]:
    """Poll until an element matching `selector` is on screen."""
    active = _active(selector)
    if not active:
        raise ValueError("expect_visible needs a selector: ref / text / contains / desc / id / cls")
    started = time.monotonic()
    try:
        element = session.wait_for(timeout_s, **selector)
    except LookupError:
        return _fail(
            f"nothing matching {active} appeared within {timeout_s}s",
            selector=active,
            waited_s=round(time.monotonic() - started, 2),
            screen=session.screen_text(),
        )
    return _pass(
        selector=active,
        found=element.to_dict(),
        waited_s=round(time.monotonic() - started, 2),
    )


def gone(session: Session, timeout_s: float = 10.0, **selector: Any) -> dict[str, Any]:
    """Poll until nothing matches `selector` — for dismissals and loading spinners."""
    active = _active(selector)
    if not active:
        raise ValueError("expect_gone needs a selector: ref / text / contains / desc / id / cls")
    started = time.monotonic()
    try:
        session.wait_until_gone(timeout_s, **selector)
    except TimeoutError as e:
        return _fail(
            str(e),
            selector=active,
            waited_s=round(time.monotonic() - started, 2),
            screen=session.screen_text(),
        )
    return _pass(selector=active, waited_s=round(time.monotonic() - started, 2))


def log_matches(
    session: Session,
    cfg: Config,
    pattern: str,
    timeout_s: float = 30.0,
    poll_s: float = 1.0,
    only_app: bool = True,
    level: str | None = None,
    lines: int = 4000,
) -> dict[str, Any]:
    """Poll logcat until `pattern` (a regex) shows up.

    Clear the buffer first — `logcat_clear`, or just start a run, which does it
    for you — or a match left over from a previous attempt will pass this.
    """
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"{pattern!r} is not a valid regex: {e}") from e

    pkg = cfg.app.package if (only_app and cfg.app.package) else None
    started = time.monotonic()
    deadline = started + timeout_s
    found: list[str] = []
    while True:
        found = adb.logcat_dump(session.serial, lines=lines, pkg=pkg, pattern=pattern, level=level)
        if found:
            return _pass(
                pattern=pattern,
                count=len(found),
                matches=found[-10:],
                waited_s=round(time.monotonic() - started, 2),
            )
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_s)

    tail = adb.logcat_dump(session.serial, lines=40, pkg=pkg, level=level)
    return _fail(
        f"no logcat line matched {pattern!r} within {timeout_s}s",
        pattern=pattern,
        waited_s=round(time.monotonic() - started, 2),
        tail=tail[-25:],
    )


def scan_crashes(lines: list[str], pkg: str | None = None) -> list[dict[str, Any]]:
    """Pull crash records out of raw logcat lines.

    When `pkg` is given, a Java crash is only reported if its `Process:` line
    names that package — otherwise every unrelated system crash on the device
    would fail the assertion, which trains an agent to ignore it.
    """
    crashes: list[dict[str, Any]] = []
    last_index = -CRASH_CONTEXT_LINES
    for i, line in enumerate(lines):
        for kind, rx in CRASH_PATTERNS:
            match = rx.search(line)
            if not match:
                continue
            excerpt = lines[max(0, i - CRASH_LOOKBACK_LINES) : i + CRASH_CONTEXT_LINES]
            if pkg:
                named = pkg in "\n".join(excerpt)
                if kind == "anr" and match.lastindex:
                    named = match.group(1) == pkg
                if not named:
                    continue
            # One dying process writes several markers (signal, then tombstone);
            # reporting them as separate crashes would overstate what happened.
            if i - last_index < CRASH_CONTEXT_LINES and crashes:
                break
            last_index = i
            crashes.append({"kind": kind, "line": line.strip(), "excerpt": excerpt})
            break
    return crashes


def no_crash(
    session: Session,
    cfg: Config,
    pkg: str | None = None,
    lines: int = 4000,
) -> dict[str, Any]:
    """Assert nothing in the log says the app died.

    Reads the dedicated `crash` buffer as well as `main`: a native abort or a
    tombstone never reaches `main` at all, so a check that only reads `main`
    quietly passes on the worst class of failure there is.
    """
    target = pkg or cfg.app.package
    log_lines = adb.logcat_dump(session.serial, lines=lines, buffers="main,crash")
    crashes = scan_crashes(log_lines, target)
    if crashes:
        first = crashes[0]
        return _fail(
            f"{len(crashes)} crash record(s) in the log; first is {first['kind']}",
            pkg=target,
            crashes=[{"kind": c["kind"], "line": c["line"]} for c in crashes],
            excerpt=first["excerpt"],
        )
    return _pass(pkg=target, scanned_lines=len(log_lines))
