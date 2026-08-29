"""Per-server session state: which device is selected, its driver, its last screen.

The `#N` references handed out by `screen()` are only meaningful against the
hierarchy they were produced from, so the session caches that snapshot and
invalidates it after anything that could change the display. `resolve()` refreshes
transparently when the cache is cold, which is what lets an agent call
`tap(desc=...)` without a `screen()` call in front of it.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import adb, ui
from .config import Config
from .drivers import Driver, create
from .log import log


class Session:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._serial: str | None = None
        self._driver: Driver | None = None
        self._elements: list[ui.Element] = []
        self._elements_fresh = False
        self.run_dir: Path | None = None

    # ── device ───────────────────────────────────────────────────────────────

    @property
    def serial(self) -> str:
        if self._serial is None:
            self._serial = adb.pick_device()
            log("session", f"auto-selected device {self._serial}")
        return self._serial

    @property
    def current_serial(self) -> str | None:
        """The pinned serial, or None — unlike `.serial`, never picks a device."""
        return self._serial

    def select(self, serial: str) -> None:
        online = adb.list_serials()
        if serial not in online:
            raise ValueError(f"{serial!r} is not attached. Available: {online or '(none)'}")
        self._reset()
        self._serial = serial
        log("session", f"device pinned to {serial}")

    def _reset(self) -> None:
        if self._driver is not None:
            self._driver.close()
        self._driver = None
        self._serial = None
        self.invalidate()

    @property
    def driver(self) -> Driver:
        if self._driver is None:
            self._driver = create(self.serial, self.cfg.driver.backend, self.cfg.timing.click_settle_s)
        return self._driver

    # ── screen ───────────────────────────────────────────────────────────────

    def invalidate(self) -> None:
        """Mark the cached screen index stale. Call after anything that can redraw."""
        self._elements_fresh = False

    def refresh(self) -> list[ui.Element]:
        self._elements = ui.parse(self.driver.dump_hierarchy())
        self._elements_fresh = True
        return self._elements

    def elements(self, refresh: bool = False) -> list[ui.Element]:
        if refresh or not self._elements_fresh:
            return self.refresh()
        return self._elements

    def header(self) -> str:
        app = self.driver.current_app()
        width, height = self.driver.screen_size()
        return (
            f"device={self.serial} app={app['package'] or '?'}/{app['activity'] or '?'} "
            f"screen={width}x{height} driver={self.driver.name}"
        )

    def resolve(self, **selector) -> ui.Element:
        """Find one element, retrying once against a fresh snapshot before failing.

        A stale cache is the single most common cause of a "not found" here, and
        re-reading is far cheaper than making the agent debug it.
        """
        try:
            return ui.find(self.elements(), **selector)
        except LookupError:
            if self._elements_fresh:
                raise
            return ui.find(self.refresh(), **selector)

    def wait_for(self, timeout_s: float, poll_s: float = 0.5, **selector) -> ui.Element:
        deadline = time.monotonic() + timeout_s
        last: Exception | None = None
        while True:
            try:
                return ui.find(self.refresh(), **selector)
            except LookupError as e:
                last = e
                if time.monotonic() >= deadline:
                    raise LookupError(f"{e} (waited {timeout_s}s)") from last
                time.sleep(poll_s)

    def wait_until_gone(self, timeout_s: float, poll_s: float = 0.5, **selector) -> None:
        """Block until nothing matches `selector`. Raises TimeoutError if it stays."""
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                element = ui.find(self.refresh(), **selector)
            except LookupError:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{element.label()!r} was still on screen after {timeout_s}s")
            time.sleep(poll_s)

    def screen_text(self) -> str:
        """The compact screen index, for pasting into a failure message."""
        try:
            return ui.render(self.elements(), header=self.header())
        except Exception as e:  # a failure report must never fail
            return f"(could not read the screen: {type(e).__name__}: {e})"
