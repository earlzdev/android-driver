"""Backend selection."""

from __future__ import annotations

from ..log import log
from .adb_driver import AdbDriver
from .base import Driver, DriverError


def create(serial: str, backend: str = "auto", click_settle_s: float = 0.25) -> Driver:
    """Build a driver for `serial`.

    `auto` prefers uiautomator2 and falls back to the pure-adb backend, logging
    which one won so a confused operator can see it in the server's stderr.
    """
    if backend == "adb":
        return AdbDriver(serial, click_settle_s)

    try:
        from .u2_driver import U2Driver

        driver = U2Driver(serial, click_settle_s)
        log("driver", f"{serial}: using uiautomator2")
        return driver
    except Exception as e:
        if backend == "uiautomator2":
            raise DriverError(str(e)) from e
        log("driver", f"{serial}: uiautomator2 unavailable ({e}); falling back to the adb backend")
        return AdbDriver(serial, click_settle_s)
