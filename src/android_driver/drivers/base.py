"""The driver interface, plus the behaviour both backends share."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

from .. import adb
from ..log import log
from ..ui import Element


class DriverError(RuntimeError):
    pass


# Friendly key names → Android keycodes. The names match what an agent would
# guess; unknown names fall through as-is so raw KEYCODE_* still works.
KEYCODES = {
    "home": "KEYCODE_HOME",
    "back": "KEYCODE_BACK",
    "menu": "KEYCODE_MENU",
    "enter": "KEYCODE_ENTER",
    "search": "KEYCODE_SEARCH",
    "delete": "KEYCODE_DEL",
    "backspace": "KEYCODE_DEL",
    "tab": "KEYCODE_TAB",
    "space": "KEYCODE_SPACE",
    "power": "KEYCODE_POWER",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
    "camera": "KEYCODE_CAMERA",
    "app_switch": "KEYCODE_APP_SWITCH",
    "recent": "KEYCODE_APP_SWITCH",
    "wake": "KEYCODE_WAKEUP",
    "sleep": "KEYCODE_SLEEP",
    "up": "KEYCODE_DPAD_UP",
    "down": "KEYCODE_DPAD_DOWN",
    "left": "KEYCODE_DPAD_LEFT",
    "right": "KEYCODE_DPAD_RIGHT",
    "center": "KEYCODE_DPAD_CENTER",
}


class Driver(ABC):
    """One device, one driver. Coordinates are always device pixels."""

    name = "base"

    def __init__(self, serial: str, click_settle_s: float = 0.25) -> None:
        self.serial = serial
        self.click_settle_s = click_settle_s

    # ── required of every backend ────────────────────────────────────────────

    @abstractmethod
    def dump_hierarchy(self) -> str: ...

    @abstractmethod
    def screenshot(self, path: Path) -> Path: ...

    @abstractmethod
    def _click(self, x: int, y: int) -> None: ...

    @abstractmethod
    def long_click(self, x: int, y: int, duration_s: float = 1.0) -> None: ...

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float = 0.3) -> None: ...

    @abstractmethod
    def press(self, key: str) -> None: ...

    @abstractmethod
    def set_text(self, element: Element, text: str) -> None:
        """Replace the contents of a text field with `text`."""

    # ── shared ───────────────────────────────────────────────────────────────

    def click(self, x: int, y: int) -> None:
        """Tap, then let the UI settle.

        The settle is not cosmetic. Many Compose buttons surface as
        `android.view.View` with `clickable=false` in the accessibility tree, so a
        hierarchy query issued immediately after a tap reads pre-animation state
        and reports the *old* screen — which looks exactly like a missed tap.
        """
        self._click(x, y)
        time.sleep(self.click_settle_s)

    def screen_size(self) -> tuple[int, int]:
        raw = adb.shell(self.serial, "wm", "size", check=False).strip()
        for part in reversed(raw.split()):
            if "x" in part:
                w, _, h = part.partition("x")
                if w.isdigit() and h.isdigit():
                    return int(w), int(h)
        raise DriverError(f"could not parse screen size from {raw!r}")

    def current_app(self) -> dict[str, str]:
        """Package and activity currently in the foreground."""
        out = adb.shell(
            self.serial, "dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity'",
            check=False,
        )
        for line in out.splitlines():
            for raw in line.split():
                # The component sits inside an ActivityRecord{...} blob, so the
                # token can carry a trailing brace or comma.
                token = raw.strip("{},")
                if "/" in token and "." in token:
                    pkg, _, activity = token.partition("/")
                    return {"package": pkg, "activity": activity}
        return {"package": "", "activity": ""}

    def keyboard_is_shown(self) -> bool:
        """Authoritative across OEMs: `mInputShown=true` in the IME dump."""
        try:
            out = adb.shell(
                self.serial, "dumpsys input_method | grep mInputShown", check=False, timeout=20
            )
        except Exception:
            return False
        return "mInputShown=true" in out

    def dismiss_keyboard(self) -> None:
        """Close the soft keyboard — but only when it is actually open.

        Pressing Back unconditionally is a classic way to lose an hour: with no
        keyboard up, Back dismisses whatever dialog or screen owns focus instead,
        and the failure surfaces three steps later as a missing element.
        """
        if not self.keyboard_is_shown():
            return
        self.press("back")
        time.sleep(0.3)

    def close(self) -> None:
        return None

    def _keycode(self, key: str) -> str:
        return KEYCODES.get(key.lower(), key if key.startswith("KEYCODE_") else f"KEYCODE_{key.upper()}")

    def _log(self, msg: str) -> None:
        log(f"driver:{self.name}", msg)
