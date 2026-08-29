"""Zero-setup backend: `uiautomator dump` + `input`, nothing installed on device.

Slower than uiautomator2 (a hierarchy dump costs roughly a second) and weaker at
text entry, but it runs anywhere adb runs — CI containers, corporate-managed
devices, anywhere you cannot or will not install a helper APK.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path

from .. import adb
from ..ui import Element
from .base import Driver, DriverError

REMOTE_DUMP = "/sdcard/android-driver-dump.xml"


class AdbDriver(Driver):
    name = "adb"

    def dump_hierarchy(self, retries: int = 3) -> str:
        """Dump the window hierarchy.

        `uiautomator dump` refuses to run while the window is animating, reporting
        "could not get idle state". That is a transient condition right after a tap,
        so we retry rather than surfacing it — an agent cannot do anything useful
        with it anyway.
        """
        last = ""
        for attempt in range(retries):
            result = adb.shell_result(self.serial, f"uiautomator dump {REMOTE_DUMP}", timeout=60)
            combined = result["stdout"] + result["stderr"]
            if "dumped to" in combined or "UI hierchary dumped" in combined:
                xml = adb.shell_result(self.serial, f"cat {REMOTE_DUMP}", timeout=60)["stdout"]
                if xml.lstrip().startswith("<"):
                    return xml
                last = "dump file was empty or not XML"
            else:
                last = combined.strip()
            if attempt < retries - 1:
                self._log(f"hierarchy dump retry {attempt + 1}/{retries}: {last}")
                time.sleep(1.0)
        raise DriverError(f"uiautomator dump failed after {retries} attempts: {last}")

    def screenshot(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # exec-out keeps the PNG binary-clean; `adb shell screencap -p` mangles
        # newlines on some hosts.
        with path.open("wb") as fh:
            result = subprocess.run(
                ["adb", "-s", self.serial, "exec-out", "screencap", "-p"],
                stdout=fh,
                stderr=subprocess.PIPE,
                check=False,
                timeout=120,
            )
        if result.returncode != 0 or path.stat().st_size == 0:
            raise DriverError(f"screencap failed: {result.stderr.decode(errors='replace').strip()}")
        return path

    def _click(self, x: int, y: int) -> None:
        adb.shell(self.serial, "input", "tap", str(x), str(y))

    def long_click(self, x: int, y: int, duration_s: float = 1.0) -> None:
        ms = int(duration_s * 1000)
        adb.shell(self.serial, "input", "swipe", str(x), str(y), str(x), str(y), str(ms))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float = 0.3) -> None:
        ms = int(duration_s * 1000)
        adb.shell(self.serial, "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))

    def press(self, key: str) -> None:
        adb.shell(self.serial, "input", "keyevent", self._keycode(key))

    def set_text(self, element: Element, text: str) -> None:
        """Tap the field, clear it, then type.

        This is the fragile path — on Jetpack Compose the tap does not always move
        focus, and the text can land in a sibling field. The uiautomator2 backend
        writes to the node directly and does not have this problem; prefer it when
        the app under test uses Compose.
        """
        x, y = element.center
        self.click(x, y)
        # Move the caret to the end, then backspace over whatever was there. The
        # field's current text gives us the count; the margin covers content that
        # scrolled out of the accessibility snapshot.
        self.press("KEYCODE_MOVE_END")
        deletions = len(element.text) + 8
        adb.shell(self.serial, "input", "keyevent", *(["KEYCODE_DEL"] * deletions), check=False)
        if text:
            adb.shell(self.serial, "input", "text", shlex.quote(self._escape(text)))
        time.sleep(0.2)
        self.dismiss_keyboard()

    @staticmethod
    def _escape(text: str) -> str:
        """`input text` treats a space as an argument separator and %s literally."""
        return text.replace("%", "%%").replace(" ", "%s")
