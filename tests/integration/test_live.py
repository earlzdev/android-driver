"""End-to-end against a real emulator: the paths a fake device cannot prove."""

from __future__ import annotations

import os
import time

import pytest

from android_driver import actions, adb, emulator, expect, ui
from android_driver import recipes as R
from android_driver.run import Runs

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("ANDROID_DRIVER_LIVE") != "1",
        reason="set ANDROID_DRIVER_LIVE=1 with an emulator attached to run the live suite",
    ),
]

SETTINGS = "com.android.settings"
SNAPSHOT = "android-driver-selftest"


def test_device_reports_itself(live):
    info = adb.device_info(live.serial)
    assert info["sdk"].isdigit() and int(info["sdk"]) >= 21
    assert "x" in info["screen"]
    assert emulator.is_booted(live.serial)


def test_driver_backend_resolved(live):
    assert live.driver.name in {"uiautomator2", "adb"}
    width, height = live.driver.screen_size()
    assert width > 0 and height > 0


def test_screen_index_is_readable_and_small(live):
    actions.press_key(live, "home")
    time.sleep(1)
    elements = live.refresh()
    rendered = ui.render(elements, header=live.header())
    assert rendered.startswith(f"device={live.serial}")
    raw = live.driver.dump_hierarchy()
    assert len(rendered) < len(raw) / 4, "the index should be far smaller than the XML"
    for element in elements:
        assert element.bounds[2] > element.bounds[0]


def test_screenshot_writes_a_real_png(live, tmp_path):
    path = actions.screenshot(live, tmp_path / "shot.png")
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert path.stat().st_size > 5000


def test_shell_round_trip_including_a_pipe(live):
    result = actions.shell(live, "getprop | grep ro.build.version.sdk")
    assert result["ok"] and "sdk" in result["stdout"]


def test_logcat_clear_then_read(live):
    adb.logcat_clear(live.serial)
    adb.shell(live.serial, "log", "-t", "android_driver", "hello-from-the-selftest")
    lines = adb.logcat_dump(live.serial, lines=200, pattern="hello-from-the-selftest")
    assert lines, "the tagged line should be in the buffer we just cleared"


def test_launching_a_system_app_moves_the_foreground(live):
    actions.launch_app(live, live.cfg, pkg=SETTINGS)
    assert live.driver.current_app()["package"] == SETTINGS
    actions.press_key(live, "home")
    time.sleep(1)
    assert live.driver.current_app()["package"] != SETTINGS


def test_app_info_for_an_installed_and_a_missing_package(live):
    assert adb.app_info(live.serial, SETTINGS)["installed"] is True
    assert adb.app_info(live.serial, "com.nope.nothing.here")["installed"] is False


def test_expectations_against_a_real_screen(live, live_cfg):
    actions.launch_app(live, live_cfg, pkg=SETTINGS)
    time.sleep(1)
    elements = live.refresh()
    labelled = next((e for e in elements if e.text), None)
    if labelled is None:
        pytest.skip("no labelled element on the settings screen to assert against")
    assert expect.visible(live, timeout_s=5, text=labelled.text)["passed"] is True
    assert expect.visible(live, timeout_s=1, text="!!! definitely not here !!!")["passed"] is False
    assert expect.gone(live, timeout_s=1, text="!!! definitely not here !!!")["passed"] is True
    assert expect.no_crash(live, live_cfg, pkg=SETTINGS)["passed"] is True


def test_a_recipe_runs_against_the_device(live, live_cfg, runs):
    recipe = R.parse(
        "selftest",
        {
            "params": {"pkg": {"default": SETTINGS}},
            "steps": [
                {"launch": {"pkg": "{{pkg}}"}},
                {"sleep": 1},
                {"screenshot": "settings"},
                {"press": "home"},
                {"expect_no_crash": {"pkg": "{{pkg}}"}},
            ],
        },
    )
    result = R.Runner(R.Context(live, live_cfg, runs), {}).run(recipe, {})
    assert result["ok"] is True, result.get("error")
    assert [s["status"] for s in result["steps"]] == ["ok"] * 5


def test_a_run_bundle_is_written(live, live_cfg):
    runs = Runs(live_cfg)
    runs.start(live, "selftest")
    actions.press_key(live, "home")
    runs.record_event("press_key", "ok", 0.1, {"key": "home"})
    result = runs.end(live)
    run_dir = live_cfg.runs_dir / result["run_id"]
    assert (run_dir / "report.md").is_file()
    assert (run_dir / "timeline.json").is_file()
    assert (run_dir / "logcat.txt").stat().st_size > 0


def test_failure_capture_produces_usable_artifacts(live, runs):
    with pytest.raises(LookupError):
        actions.tap(live, desc="definitely-not-on-this-screen")
    captured = runs.capture(live, "tap")
    assert captured["screenshot"].endswith(".png")
    assert "<hierarchy" in open(captured["hierarchy"]).read()


@pytest.mark.slow
def test_snapshot_round_trip_is_fast_and_restores_state(live):
    if not live.serial.startswith("emulator-"):
        pytest.skip("snapshots are emulator-only")

    actions.launch_app(live, live.cfg, pkg=SETTINGS)
    time.sleep(1)
    saved = emulator.snapshot_save(live.serial, SNAPSHOT)
    assert saved["ok"] and SNAPSHOT in emulator.snapshot_list(live.serial)

    actions.press_key(live, "home")
    time.sleep(1)
    assert live.driver.current_app()["package"] != SETTINGS

    loaded = emulator.snapshot_load(live.serial, SNAPSHOT)
    assert loaded["ok"]
    live.invalidate()
    time.sleep(2)
    assert live.driver.current_app()["package"] == SETTINGS, "the snapshot should restore the foreground"
    # The whole premise: restoring is cheap enough to do between every attempt.
    assert loaded["seconds"] < 30

    emulator.snapshot_delete(live.serial, SNAPSHOT)
    assert SNAPSHOT not in emulator.snapshot_list(live.serial)


@pytest.mark.slow
def test_screen_recording_round_trip(live, tmp_path):
    from android_driver.record import Recorder

    recorder = Recorder()
    recorder.start(live.serial, name="selftest", time_limit_s=10)
    actions.press_key(live, "home")
    time.sleep(3)
    result = recorder.stop(tmp_path / "clip.mp4")
    assert result["bytes"] > 1000
