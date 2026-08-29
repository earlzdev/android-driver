"""Run bundles: the evidence a run leaves behind."""

from __future__ import annotations

import json

import pytest

from android_driver import actions
from android_driver.run import Runs


@pytest.fixture
def runs(cfg, monkeypatch):
    info = {"serial": "emulator-test", "model": "Fake"}
    monkeypatch.setattr("android_driver.run.adb.device_info", lambda serial: info)
    monkeypatch.setattr("android_driver.run.adb.logcat_clear", lambda serial: None)
    monkeypatch.setattr("android_driver.run.adb.logcat_dump", lambda serial, **kw: ["one log line"])
    return Runs(cfg)


def test_a_run_writes_a_report_a_timeline_and_a_log(runs, session):
    started = runs.start(session, "login repro", note="issue 412")
    runs.record_event("tap", "ok", 0.4, {"tapped": "Sign in"})
    runs.record_event("expect_visible", "failed", 10.0, {"error": "LookupError: not found"})
    ended = runs.end(session)

    assert ended["run_id"] == started["run_id"]
    assert ended["passed"] is False and ended["failed"] == ["expect_visible"]

    run_dir = runs.root / ended["run_id"]
    timeline = json.loads((run_dir / "timeline.json").read_text())
    assert [e["tool"] for e in timeline["events"]] == ["tap", "expect_visible"]
    assert timeline["device"]["model"] == "Fake"
    assert timeline["note"] == "issue 412"

    report = (run_dir / "report.md").read_text()
    assert "# Run " in report and "| `tap` | ok |" in report
    assert "LookupError: not found" in report
    assert (run_dir / "logcat.txt").read_text().strip() == "one log line"


def test_run_id_is_a_readable_slug(runs, session):
    result = runs.start(session, "Login / repro #4")
    assert result["run_id"].endswith("-login-repro-4")


def test_starting_a_second_run_closes_the_first(runs, session):
    first = runs.start(session, "one")["run_id"]
    runs.start(session, "two")
    assert (runs.root / first / "report.md").is_file()
    assert runs.current.name == "two"


def test_ending_without_a_run_is_an_error(runs, session):
    with pytest.raises(RuntimeError, match="no run is open"):
        runs.end(session)


def test_events_outside_a_run_are_dropped_not_stored(runs):
    runs.record_event("tap", "ok", 0.1)  # must not raise
    assert runs.current is None


def test_failure_artifacts_land_in_the_open_run(runs, session):
    runs.start(session, "bug")
    captured = runs.capture(session, "tap")
    assert captured["screenshot"].startswith(str(runs.current.dir))
    assert "login_button" in open(captured["hierarchy"]).read()


def test_failure_artifacts_without_a_run_go_to_a_fallback_dir(runs, session):
    captured = runs.capture(session, "tap")
    assert "failures" in captured["screenshot"]


def test_capture_never_raises_on_a_dead_device(runs, session, driver):
    def boom(*args, **kwargs):
        raise RuntimeError("device offline")

    driver.dump_hierarchy = boom
    driver.screenshot = boom
    assert runs.capture(session, "tap") == {}
    assert not (runs.root / "failures").exists() or not any((runs.root / "failures").iterdir())


def test_screenshots_taken_during_a_run_are_part_of_it(runs, session):
    runs.start(session, "shots")
    path = runs.artifact_dir("screenshots") / "before.png"
    actions.screenshot(session, path)
    runs.end(session)
    assert "before.png" in (runs.root / path.parent.name / "report.md").read_text()


def test_list_runs_is_newest_first_with_a_verdict(runs, session):
    runs.start(session, "one")
    runs.end(session)
    runs.start(session, "two")
    runs.record_event("tap", "failed", 0.1, {"error": "x"})
    runs.end(session)
    listed = runs.list_runs()
    assert [r["name"] for r in listed] == ["two", "one"]
    assert listed[0]["failed"] == ["tap"] and listed[1]["failed"] == []
