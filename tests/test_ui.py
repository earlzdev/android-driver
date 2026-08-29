"""The screen index: what gets shown, how it reads, and how selectors resolve."""

from __future__ import annotations

import pytest

from android_driver import ui

from .conftest import hierarchy


@pytest.fixture
def elements() -> list[ui.Element]:
    return ui.parse(hierarchy("login_screen"))


def test_drops_noise_and_keeps_substance(elements):
    labels = [e.label() for e in elements]
    assert "Sign in to continue" in labels
    assert "Sign in" in labels  # the button labels itself with its text, not its desc
    assert "login_button" in [e.desc for e in elements]
    # zero-area, and an ImageView with nothing to say, are not worth a line
    assert "Hidden" not in labels
    assert not [e for e in elements if e.cls == "android.widget.ImageView"]


def test_empty_edittexts_are_always_listed(elements):
    fields = [e for e in elements if e.cls == "android.widget.EditText"]
    assert [e.desc for e in fields] == ["text_field_Email", "text_field_Password"]


def test_render_is_compact_and_carries_refs(elements):
    rendered = ui.render(elements)
    assert rendered.splitlines()[0].startswith("#1 [Text] \"Sign in to continue\"")
    assert 'hint="Email"' in rendered
    assert "(password)" in rendered
    assert "(unchecked)" in rendered
    assert "(disabled)" in rendered
    assert "@(540,1440)" in rendered  # the Sign in button's centre
    # the whole point: far smaller than the XML it came from
    assert len(rendered) < len(hierarchy("login_screen")) / 4


def test_find_by_ref_text_desc_and_id(elements):
    assert ui.find(elements, desc="login_button").text == "Sign in"
    assert ui.find(elements, rid="login_button").text == "Sign in"
    assert ui.find(elements, rid="com.example.app:id/login_button").text == "Sign in"
    button = ui.find(elements, desc="login_button")
    assert ui.find(elements, ref=f"#{button.ref}") is button
    assert ui.find(elements, ref=button.ref) is button


def test_text_is_exact_and_contains_is_not(elements):
    # two elements say "Sign in"; the Button is first in document order
    assert ui.find(elements, text="Sign in").cls == "android.widget.Button"
    assert ui.find(elements, text="Sign in", index=1).cls == "android.widget.TextView"
    assert ui.find(elements, contains="sign in").text == "Sign in to continue"
    with pytest.raises(LookupError):
        ui.find(elements, text="Sign")


def test_combined_selectors_narrow(elements):
    assert ui.find(elements, text="Sign in", cls="Text").cls == "android.widget.TextView"


def test_useful_errors(elements):
    with pytest.raises(LookupError, match="no element matches"):
        ui.find(elements, desc="nope")
    with pytest.raises(LookupError, match="index 5 is out of range"):
        ui.find(elements, text="Sign in", index=5)
    with pytest.raises(ValueError, match="no selector given"):
        ui.find(elements)


def test_parse_rejects_junk():
    with pytest.raises(ValueError, match="could not parse"):
        ui.parse("not xml at all")


def test_empty_screen_says_so():
    assert "no interactive or readable elements" in ui.render([])
