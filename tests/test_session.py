"""Session lifecycle: what survives a device that was swapped out underneath us."""

from __future__ import annotations

from android_driver import server
from android_driver.session import Session

from .conftest import FakeDriver


def test_reconnect_drops_the_driver_but_keeps_the_device(session: Session) -> None:
    """The device is still the one the user picked; only the connection to it is gone."""
    session.reconnect()
    assert session._driver is None
    assert session.current_serial == "emulator-test"


def test_reconnect_marks_the_screen_stale(session: Session) -> None:
    session.elements()
    assert session._elements_fresh
    session.reconnect()
    assert not session._elements_fresh


def test_reconnect_survives_a_driver_whose_far_end_is_already_gone(session: Session) -> None:
    """Closing a connection to a device that no longer exists raises; that must not propagate."""

    def boom() -> None:
        raise OSError("Remote end closed connection without response")

    session._driver.close = boom  # type: ignore[method-assign]
    session.reconnect()
    assert session._driver is None


def test_the_next_call_builds_a_fresh_driver(monkeypatch, session: Session) -> None:
    built: list[str] = []

    def fake_create(serial: str, backend: str, click_settle_s: float) -> FakeDriver:
        built.append(serial)
        return FakeDriver()

    monkeypatch.setattr("android_driver.session.create", fake_create)
    session.reconnect()
    assert session.driver is not None
    assert built == ["emulator-test"]


def test_reset_clears_the_device_too(session: Session) -> None:
    session._reset()
    assert session._driver is None
    assert session.current_serial is None


def test_snapshot_load_reconnects(monkeypatch, wired, session: Session) -> None:
    """A snapshot restore takes the on-device uiautomator server with it.

    Without this the held connection fails on the *next* call with
    `RemoteDisconnected`, which reads as a broken app rather than a stale session
    — and `/android-driver:repro` calls `snapshot_load` between every attempt.
    """
    monkeypatch.setattr(
        "android_driver.emulator.snapshot_load", lambda serial, name: {"loaded": name}
    )
    assert session._driver is not None
    result = server.snapshot_load("clean")
    assert result["ok"] is True
    assert session._driver is None, "snapshot_load must drop the stale connection"


def test_stopping_the_selected_emulator_reconnects(monkeypatch, wired, session: Session) -> None:
    monkeypatch.setattr("android_driver.emulator.stop", lambda serial: {"stopped": serial})
    server.stop_emulator()
    assert session._driver is None


def test_stopping_a_different_emulator_leaves_this_session_alone(
    monkeypatch, wired, session: Session
) -> None:
    monkeypatch.setattr("android_driver.emulator.stop", lambda serial: {"stopped": serial})
    server.stop_emulator(serial="emulator-9999")
    assert session._driver is not None
