"""UI driver backends.

Two implementations behind one interface:

  * `uiautomator2` — fast, and its accessibility SET_TEXT path is the only
    reliable way to fill a Jetpack Compose TextField. Needs a one-time
    per-device `python -m uiautomator2 init`, which installs a helper APK.
  * `adb` — pure `uiautomator dump` + `input`. Slower and weaker at text entry,
    but needs nothing on the device, so it works in CI containers and on locked
    down hardware where you cannot install a helper.

`create()` picks between them; `driver.backend: auto` in the project config
prefers uiautomator2 and falls back silently.
"""

from __future__ import annotations

from .adb_driver import AdbDriver
from .base import Driver, DriverError
from .factory import create

__all__ = ["AdbDriver", "Driver", "DriverError", "create"]
