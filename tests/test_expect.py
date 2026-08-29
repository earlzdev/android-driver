"""Assertions: what passes, what fails, and how much a failure explains."""

from __future__ import annotations

import pytest

from android_driver import expect

CRASH_LOG = """\
08-27 12:00:01.000  1200  1200 I ActivityManager: Start proc com.example.app
08-27 12:00:02.000  1300  1300 E AndroidRuntime: FATAL EXCEPTION: main
08-27 12:00:02.000  1300  1300 E AndroidRuntime: Process: com.example.app, PID: 1300
08-27 12:00:02.000  1300  1300 E AndroidRuntime: java.lang.NullPointerException
08-27 12:00:02.000  1300  1300 E AndroidRuntime: \tat com.example.app.Login.onCreate(Login.kt:42)
""".splitlines()

OTHER_APP_CRASH = """\
08-27 12:00:02.000  1300  1300 E AndroidRuntime: FATAL EXCEPTION: main
08-27 12:00:02.000  1300  1300 E AndroidRuntime: Process: com.vendor.launcher, PID: 1300
08-27 12:00:02.000  1300  1300 E AndroidRuntime: java.lang.IllegalStateException
""".splitlines()

ANR_LOG = ["08-27 12:00:09.000  1200  1200 E ActivityManager: ANR in com.example.app"]

NATIVE_LOG = [
    "08-27 12:00:09.000  9000  9000 F DEBUG   : pid: 9000, name: com.example.app",
    "08-27 12:00:09.000  9000  9000 F DEBUG   : signal 11 (SIGSEGV), code 1, fault addr 0x0",
]


def test_visible_passes_and_reports_what_it_found(session):
    result = expect.visible(session, timeout_s=1, desc="login_button")
    assert result["ok"] is True and result["passed"] is True
    assert result["found"]["text"] == "Sign in"


def test_visible_failure_carries_the_screen_that_was_there(session):
    result = expect.visible(session, timeout_s=0.1, text="Welcome")
    assert result["ok"] is False and result["passed"] is False
    assert "did not" in result["error"] or "appeared" in result["error"]
    assert "login_button" in result["screen"]  # the agent can see what it got instead


def test_visible_polls_until_the_screen_changes(session, driver):
    driver.advance("home_screen")
    assert expect.visible(session, timeout_s=1, text="Welcome")["passed"] is True


def test_gone_passes_once_the_element_leaves(session, driver):
    assert expect.gone(session, timeout_s=0.1, text="Welcome")["passed"] is True
    driver.advance("home_screen")
    result = expect.gone(session, timeout_s=0.2, desc="login_button")
    assert result["passed"] is True


def test_gone_fails_while_the_element_stays(session):
    result = expect.gone(session, timeout_s=0.2, desc="login_button")
    assert result["passed"] is False
    assert "still on screen" in result["error"]


def test_a_selector_is_required(session):
    with pytest.raises(ValueError, match="needs a selector"):
        expect.visible(session, timeout_s=0.1)


def test_scan_crashes_finds_a_java_crash():
    crashes = expect.scan_crashes(CRASH_LOG, "com.example.app")
    assert [c["kind"] for c in crashes] == ["fatal_exception"]
    assert "NullPointerException" in "\n".join(crashes[0]["excerpt"])


def test_scan_crashes_ignores_another_app(): 
    assert expect.scan_crashes(OTHER_APP_CRASH, "com.example.app") == []
    assert len(expect.scan_crashes(OTHER_APP_CRASH, None)) == 1


def test_scan_crashes_recognises_anr_and_native_aborts():
    assert expect.scan_crashes(ANR_LOG, "com.example.app")[0]["kind"] == "anr"
    assert expect.scan_crashes(ANR_LOG, "com.other.app") == []
    assert expect.scan_crashes(NATIVE_LOG, "com.example.app")[0]["kind"] == "native_crash"


def test_no_crash_reads_the_crash_buffer(session, cfg, monkeypatch):
    seen = {}

    def fake_dump(serial, **kwargs):
        seen.update(kwargs)
        return CRASH_LOG

    monkeypatch.setattr(expect.adb, "logcat_dump", fake_dump)
    result = expect.no_crash(session, cfg)
    assert result["passed"] is False
    assert seen["buffers"] == "main,crash"  # a native abort never reaches `main`
    assert result["crashes"][0]["kind"] == "fatal_exception"


def test_no_crash_passes_on_a_quiet_log(session, cfg, monkeypatch):
    monkeypatch.setattr(expect.adb, "logcat_dump", lambda serial, **kw: ["all is well"])
    assert expect.no_crash(session, cfg)["passed"] is True


def test_expect_log_rejects_a_bad_regex(session, cfg):
    with pytest.raises(ValueError, match="not a valid regex"):
        expect.log_matches(session, cfg, "((", timeout_s=0.1)


def test_expect_log_passes_on_a_match(session, cfg, monkeypatch):
    monkeypatch.setattr(expect.adb, "logcat_dump", lambda serial, **kw: ["session.state CONNECTED"])
    result = expect.log_matches(session, cfg, "CONNECTED", timeout_s=0.1)
    assert result["passed"] is True and result["count"] == 1


def test_expect_log_failure_shows_the_tail(session, cfg, monkeypatch):
    monkeypatch.setattr(
        expect.adb, "logcat_dump", lambda serial, **kw: [] if kw.get("pattern") else ["some other line"]
    )
    result = expect.log_matches(session, cfg, "CONNECTED", timeout_s=0.1, poll_s=0.05)
    assert result["passed"] is False
    assert result["tail"] == ["some other line"]
