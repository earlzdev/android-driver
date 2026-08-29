"""Live-device fixtures. Everything here needs a real, booted emulator.

Skipped unless ANDROID_DRIVER_LIVE=1, so `pytest` stays hermetic by default and
the same suite can run in CI behind an emulator action.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from android_driver import adb
from android_driver import config as config_mod
from android_driver.run import Runs
from android_driver.session import Session


@pytest.fixture(scope="session")
def serial() -> str:
    devices = adb.list_devices()
    if not devices:
        pytest.skip("no adb device in state 'device'")
    return devices[0]["serial"]


@pytest.fixture(scope="session")
def live_cfg(tmp_path_factory) -> config_mod.Config:
    root = tmp_path_factory.mktemp("project")
    return config_mod.Config(project_root=Path(root), source=None)


@pytest.fixture(scope="session")
def live(serial: str, live_cfg: config_mod.Config) -> Session:
    session = Session(live_cfg)
    session.select(serial)
    return session


@pytest.fixture
def runs(live_cfg: config_mod.Config) -> Runs:
    return Runs(live_cfg)
