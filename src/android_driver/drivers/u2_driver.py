"""uiautomator2 backend — the default when the device-side agent is available."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from pathlib import Path

from ..ui import Element
from .base import Driver, DriverError


class U2Driver(Driver):
    name = "uiautomator2"

    def __init__(self, serial: str, click_settle_s: float = 0.25, find_timeout_s: int = 10) -> None:
        super().__init__(serial, click_settle_s)
        try:
            import uiautomator2 as u2
        except ImportError as e:  # pragma: no cover - dependency is declared
            raise DriverError("uiautomator2 is not installed") from e
        try:
            self.d = u2.connect(serial)
            self.d.implicitly_wait(find_timeout_s)
        except Exception as e:
            raise DriverError(
                f"could not connect uiautomator2 to {serial}: {e}. "
                f"Run `python -m uiautomator2 init` against the device, or set "
                "`driver.backend: adb` in your config to use the zero-setup backend."
            ) from e

    def dump_hierarchy(self) -> str:
        return self.d.dump_hierarchy()

    def screenshot(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.d.screenshot(str(path))
        return path

    def _click(self, x: int, y: int) -> None:
        self.d.click(x, y)

    def long_click(self, x: int, y: int, duration_s: float = 1.0) -> None:
        self.d.long_click(x, y, duration_s)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float = 0.3) -> None:
        self.d.swipe(x1, y1, x2, y2, duration=duration_s)

    def press(self, key: str) -> None:
        friendly = key.lower()
        if friendly in {"home", "back", "menu", "enter", "search", "delete", "recent", "power",
                        "volume_up", "volume_down", "camera", "left", "right", "up", "down", "center"}:
            self.d.press(friendly)
        else:
            self.d.shell(f"input keyevent {self._keycode(key)}")

    def set_text(self, element: Element, text: str) -> None:
        """Write directly to the target node via the accessibility SET_TEXT action.

        Tap-then-type is unreliable on Compose: focus does not always follow the
        tap and the text lands in a sibling TextField. Addressing the EditText by
        its document-order index and calling set_text bypasses focus dispatch
        entirely, which is why this indirection exists.
        """
        index = self._edittext_index(element)
        self.d(className="android.widget.EditText", instance=index).set_text(text)
        time.sleep(0.2)
        self.dismiss_keyboard()

    def _edittext_index(self, element: Element) -> int:
        """Position of `element` among all EditTexts in the current hierarchy.

        Uses a single snapshot so we do not race recomposition between locating the
        target and enumerating its siblings.
        """
        root = ET.fromstring(self.dump_hierarchy())
        edittexts = [n for n in root.iter("node") if n.attrib.get("class") == "android.widget.EditText"]
        for i, node in enumerate(edittexts):
            bounds = node.attrib.get("bounds", "")
            if bounds and _bounds_match(bounds, element.bounds):
                return i
            # Compose renders the label as a descendant View of the EditText, so the
            # content-desc we matched on may sit one level down.
            for child in node.iter("node"):
                if element.desc and child.attrib.get("content-desc") == element.desc:
                    return i
                if element.rid and child.attrib.get("resource-id") == element.rid:
                    return i
        raise DriverError(
            f"could not locate an EditText for {element.label()!r}. "
            "Call `screen` to re-read the current layout."
        )


def _bounds_match(raw: str, bounds: tuple[int, int, int, int]) -> bool:
    from ..ui import BOUNDS_RE

    m = BOUNDS_RE.match(raw)
    return bool(m) and tuple(int(g) for g in m.groups()) == bounds
