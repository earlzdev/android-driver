"""Shared fixtures: a fake device, so the whole engine is testable without an emulator."""

from __future__ import annotations

from pathlib import Path

import pytest

from android_driver import config as config_mod
from android_driver.drivers.base import Driver
from android_driver.session import Session

FIXTURES = Path(__file__).parent / "fixtures"


def hierarchy(name: str) -> str:
    return (FIXTURES / f"{name}.xml").read_text(encoding="utf-8")


class FakeDriver(Driver):
    """A driver over a scripted list of hierarchies. Records everything it is asked to do."""

    name = "fake"

    def __init__(self, screens: list[str] | None = None) -> None:
        super().__init__("emulator-test", click_settle_s=0.0)
        self.screens = screens or [hierarchy("login_screen")]
        self.calls: list[tuple] = []
        self.dumps = 0
        self.keyboard = False

    # advancing the script is how a test says "the app moved on"
    def advance(self, name: str) -> None:
        self.screens.append(hierarchy(name))

    def dump_hierarchy(self) -> str:
        self.dumps += 1
        return self.screens[-1]

    def screenshot(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n fake")
        self.calls.append(("screenshot", str(path)))
        return path

    def _click(self, x: int, y: int) -> None:
        self.calls.append(("click", x, y))

    def long_click(self, x: int, y: int, duration_s: float = 1.0) -> None:
        self.calls.append(("long_click", x, y, duration_s))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float = 0.3) -> None:
        self.calls.append(("swipe", x1, y1, x2, y2))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def set_text(self, element, text: str) -> None:
        self.calls.append(("set_text", element.label(), text))

    # the base class reaches for adb for these; the fake answers locally
    def screen_size(self) -> tuple[int, int]:
        return (1080, 2400)

    def current_app(self) -> dict[str, str]:
        return {"package": "com.example.app", "activity": ".LoginActivity"}

    def keyboard_is_shown(self) -> bool:
        return self.keyboard


@pytest.fixture
def cfg(tmp_path: Path) -> config_mod.Config:
    return config_mod.Config(
        project_root=tmp_path, source=None, app=config_mod.AppConfig(package="com.example.app")
    )


@pytest.fixture
def driver() -> FakeDriver:
    return FakeDriver()


@pytest.fixture
def session(cfg: config_mod.Config, driver: FakeDriver) -> Session:
    s = Session(cfg)
    # Pin the fake device directly: `select()` would go looking for a real one.
    s._serial = "emulator-test"
    s._driver = driver
    return s
