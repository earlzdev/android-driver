"""Device verbs, factored out of the tool layer.

Every function here raises on failure and returns a plain dict of facts on
success. The MCP tool layer turns that into `{"ok": ...}` and the recipe
interpreter calls the very same functions — so a recipe step and a hand-driven
tool call cannot drift apart, which is the whole point of the split.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import adb, ui
from . import build as build_mod
from .config import Config
from .session import Session

DIRECTIONS = ("up", "down", "left", "right")


# ── UI ────────────────────────────────────────────────────────────────────────


def tap(
    session: Session,
    *,
    ref: str | None = None,
    text: str | None = None,
    contains: str | None = None,
    desc: str | None = None,
    rid: str | None = None,
    cls: str | None = None,
    index: int = 0,
) -> dict:
    element = session.resolve(
        ref=ref, text=text, contains=contains, desc=desc, rid=rid, cls=cls, index=index
    )
    x, y = element.center
    session.driver.click(x, y)
    session.invalidate()
    return {"tapped": element.label(), "at": [x, y]}


def tap_xy(session: Session, x: int, y: int) -> dict:
    session.driver.click(x, y)
    session.invalidate()
    return {"at": [x, y]}


def long_press(
    session: Session,
    *,
    duration_s: float = 1.0,
    ref: str | None = None,
    text: str | None = None,
    contains: str | None = None,
    desc: str | None = None,
    rid: str | None = None,
    index: int = 0,
) -> dict:
    element = session.resolve(ref=ref, text=text, contains=contains, desc=desc, rid=rid, index=index)
    x, y = element.center
    session.driver.long_click(x, y, duration_s)
    session.invalidate()
    return {"long_pressed": element.label(), "at": [x, y], "duration_s": duration_s}


def type_text(
    session: Session,
    text: str,
    *,
    ref: str | None = None,
    desc: str | None = None,
    rid: str | None = None,
    contains: str | None = None,
    index: int = 0,
) -> dict:
    element = session.resolve(ref=ref, desc=desc, rid=rid, contains=contains, index=index)
    session.driver.set_text(element, text)
    session.invalidate()
    return {"field": element.label(), "text": text}


def swipe(session: Session, direction: str = "up", distance: float = 0.6, duration_s: float = 0.3) -> dict:
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {list(DIRECTIONS)}, got {direction!r}")
    width, height = session.driver.screen_size()
    cx, cy = width // 2, height // 2
    dx = int(width * distance / 2)
    dy = int(height * distance / 2)
    moves = {
        "up": (cx, cy + dy, cx, cy - dy),
        "down": (cx, cy - dy, cx, cy + dy),
        "left": (cx + dx, cy, cx - dx, cy),
        "right": (cx - dx, cy, cx + dx, cy),
    }
    session.driver.swipe(*moves[direction], duration_s=duration_s)
    session.invalidate()
    return {"direction": direction, "distance": distance}


def scroll_to(
    session: Session,
    *,
    ref: str | None = None,
    text: str | None = None,
    contains: str | None = None,
    desc: str | None = None,
    rid: str | None = None,
    direction: str = "up",
    max_swipes: int = 8,
    distance: float = 0.5,
) -> dict:
    """Swipe until a selector shows up, then stop. Raises if it never appears.

    Scrolling is a loop rather than a driver primitive because the pure-adb
    backend has no scroll-to; doing it here means both backends behave the same.
    """
    selector = {"ref": ref, "text": text, "contains": contains, "desc": desc, "rid": rid}
    if not any(v is not None for v in selector.values()):
        raise ValueError("scroll_to needs a selector: ref / text / contains / desc / rid")

    for attempt in range(max_swipes + 1):
        try:
            element = ui.find(session.refresh(), **selector)
            return {"found": element.label(), "swipes": attempt, "at": list(element.center)}
        except LookupError:
            if attempt == max_swipes:
                break
            swipe(session, direction=direction, distance=distance)
            time.sleep(0.2)
    active = {k: v for k, v in selector.items() if v is not None}
    raise LookupError(f"nothing matching {active} after {max_swipes} {direction} swipes")


def press_key(session: Session, key: str) -> dict:
    session.driver.press(key)
    session.invalidate()
    return {"key": key}


def screenshot(session: Session, path: Path) -> Path:
    return session.driver.screenshot(path)


# ── app lifecycle ─────────────────────────────────────────────────────────────


def build_app(cfg: Config) -> dict:
    return {"apk_path": str(build_mod.build(cfg))}


def install_app(
    session: Session, cfg: Config, apk_path: str | None = None, build_first: bool = False
) -> dict:
    apk = build_mod.build(cfg) if build_first else build_mod.resolve_apk(cfg, apk_path)
    result = adb.install(
        session.serial,
        apk,
        cfg.package,
        strategy=cfg.install.strategy,
        grant_runtime_perms=cfg.install.grant_runtime_perms,
        appops=cfg.install.appops or None,
    )
    session.invalidate()
    return result


def uninstall_app(session: Session, cfg: Config, pkg: str | None = None) -> dict:
    target = pkg or cfg.package
    adb.uninstall(session.serial, target)
    session.invalidate()
    return {"pkg": target}


def launch_app(session: Session, cfg: Config, pkg: str | None = None, cold: bool = True) -> dict:
    target = pkg or cfg.package
    if cold:
        adb.force_stop(session.serial, target)
    adb.launch(session.serial, target, cfg.app.activity if target == cfg.app.package else None)
    time.sleep(cfg.timing.cold_start_settle_s)
    session.invalidate()
    return {"pkg": target, "cold": cold}


def force_stop(session: Session, cfg: Config, pkg: str | None = None) -> dict:
    target = pkg or cfg.package
    adb.force_stop(session.serial, target)
    session.invalidate()
    return {"pkg": target}


def clear_app_data(session: Session, cfg: Config, pkg: str | None = None) -> dict:
    target = pkg or cfg.package
    adb.clear_data(session.serial, target)
    session.invalidate()
    return {"pkg": target}


# ── shell ─────────────────────────────────────────────────────────────────────


def shell(session: Session, cmd: str) -> dict:
    return adb.shell_result(session.serial, cmd)
