"""Device verbs: the shared layer under both the tools and the recipe engine."""

from __future__ import annotations

import pytest

from android_driver import actions


def test_tap_resolves_a_selector_to_a_centre_point(session, driver):
    result = actions.tap(session, desc="login_button")
    assert result == {"tapped": "Sign in", "at": [540, 1440]}
    assert driver.calls == [("click", 540, 1440)]


def test_tap_invalidates_the_cached_screen(session, driver):
    session.elements()
    before = driver.dumps
    actions.tap(session, desc="login_button")
    session.elements()
    assert driver.dumps == before + 1  # the screen was re-read, not reused


def test_type_text_targets_the_field_rather_than_tapping_it(session, driver):
    actions.type_text(session, "me@example.com", desc="text_field_Email")
    assert driver.calls == [("set_text", "text_field_Email", "me@example.com")]


def test_swipe_directions_map_to_the_right_gesture(session, driver):
    actions.swipe(session, "up", distance=0.5)
    actions.swipe(session, "left", distance=0.5)
    assert driver.calls[0] == ("swipe", 540, 1800, 540, 600)
    assert driver.calls[1] == ("swipe", 810, 1200, 270, 1200)


def test_swipe_rejects_a_nonsense_direction(session):
    with pytest.raises(ValueError, match="direction must be one of"):
        actions.swipe(session, "sideways")


def test_scroll_to_stops_as_soon_as_it_finds_the_target(session, driver):
    result = actions.scroll_to(session, desc="login_button")
    assert result["swipes"] == 0
    assert not [c for c in driver.calls if c[0] == "swipe"]


def test_scroll_to_swipes_until_the_target_appears(session, driver):
    swipes = {"n": 0}
    original = driver.swipe

    def counting(*args, **kwargs):
        swipes["n"] += 1
        if swipes["n"] == 2:
            driver.advance("home_screen")
        original(*args, **kwargs)

    driver.swipe = counting
    result = actions.scroll_to(session, desc="logout_button", max_swipes=5)
    assert result["swipes"] == 2


def test_scroll_to_gives_up_with_a_clear_message(session):
    with pytest.raises(LookupError, match="after 2 up swipes"):
        actions.scroll_to(session, desc="never_here", max_swipes=2)


def test_scroll_to_needs_a_selector(session):
    with pytest.raises(ValueError, match="needs a selector"):
        actions.scroll_to(session)


def test_long_press_passes_the_duration_through(session, driver):
    actions.long_press(session, desc="login_button", duration_s=2.0)
    assert driver.calls == [("long_click", 540, 1440, 2.0)]


def test_launch_uses_the_configured_activity_only_for_the_configured_app(session, cfg, monkeypatch):
    cfg.app.activity = ".MainActivity"
    cfg.timing.cold_start_settle_s = 0
    launched = []
    monkeypatch.setattr(actions.adb, "force_stop", lambda serial, pkg: None)
    monkeypatch.setattr(actions.adb, "launch", lambda serial, pkg, activity: launched.append((pkg, activity)))
    actions.launch_app(session, cfg)
    actions.launch_app(session, cfg, pkg="com.other.app")
    assert launched == [("com.example.app", ".MainActivity"), ("com.other.app", None)]
