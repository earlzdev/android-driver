"""Selector scanning and drift detection against a miniature Android project."""

from __future__ import annotations

import pytest

from android_driver import recipes as R
from android_driver import scan

KOTLIN = '''
@Composable
fun LoginScreen() {
    Button(modifier = Modifier.testTag("login_button")) { Text("Sign in") }
    TextField(modifier = Modifier.testSemanticsTag("text_field_Email"))
    Icon(contentDescription = "back_arrow")
    demoCards.forEach { item ->
        Card(testTag = "demo_${item.name}_button")
    }
}
'''

LAYOUT = """
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android">
  <Button android:id="@+id/submit_button" />
  <EditText android:id="@+id/email_input" />
</LinearLayout>
"""

STRINGS = """
<resources>
  <string name="welcome">Welcome back</string>
  <string name="sign_in">Sign in</string>
</resources>
"""

JAVA = "int id = R.id.legacy_button;"


@pytest.fixture
def project(cfg):
    root = cfg.project_root
    src = root / "app" / "src" / "main"
    (src / "java" / "com" / "example").mkdir(parents=True)
    (src / "res" / "layout").mkdir(parents=True)
    (src / "res" / "values").mkdir(parents=True)
    (src / "java" / "com" / "example" / "Login.kt").write_text(KOTLIN)
    (src / "java" / "com" / "example" / "Legacy.java").write_text(JAVA)
    (src / "res" / "layout" / "activity_main.xml").write_text(LAYOUT)
    (src / "res" / "values" / "strings.xml").write_text(STRINGS)
    # build output must not be scanned: it dwarfs the sources and is generated
    build = root / "app" / "build" / "src" / "main"
    build.mkdir(parents=True)
    (build / "Generated.kt").write_text('Modifier.testTag("generated_tag")')
    return cfg


def test_finds_tags_descs_ids_and_strings(project):
    found = scan.scan(project)
    assert "login_button" in found.by_kind["tag"]
    assert "text_field_Email" in found.by_kind["tag"]
    assert "back_arrow" in found.by_kind["desc"]
    assert {"submit_button", "email_input", "legacy_button"} <= found.by_kind["id"]
    assert "Welcome back" in found.by_kind["text"]


def test_runtime_templates_are_separated_out(project):
    found = scan.scan(project)
    assert "demo_${item.name}_button" in found.templates
    assert "demo_${item.name}_button" not in found.all


def test_build_output_is_skipped(project):
    assert "generated_tag" not in scan.scan(project).all


def test_custom_patterns_from_config(project):
    project.selectors = {"patterns": [r'byMarker\("([^"]+)"\)']}
    (project.project_root / "app" / "src" / "main" / "Extra.kt").write_text('byMarker("custom_thing")')
    assert "custom_thing" in scan.scan(project).all


def test_check_recipes_flags_a_typo_and_suggests_the_real_name(project):
    found = scan.scan(project)
    recipes = {"login": R.parse("login", {"steps": [{"tap": {"desc": "login_buton"}}]})}
    warnings = scan.check_recipes(recipes, found)
    assert len(warnings) == 1
    assert "login_buton" in warnings[0] and "Did you mean 'login_button'?" in warnings[0]


def test_check_recipes_is_quiet_when_everything_resolves(project):
    found = scan.scan(project)
    recipes = {
        "login": R.parse(
            "login",
            {"steps": [{"tap": {"desc": "login_button"}}, {"tap": {"id": "submit_button"}},
                       {"tap": {"text": "anything at all"}}]},
        )
    }
    assert scan.check_recipes(recipes, found) == []


def test_check_recipes_ignores_interpolated_selectors(project):
    recipes = {"x": R.parse("x", {"params": ["tag"], "steps": [{"tap": {"desc": "{{tag}}"}}]})}
    assert scan.check_recipes(recipes, scan.scan(project)) == []


def test_check_recipes_says_nothing_when_nothing_was_scanned(cfg):
    recipes = {"x": R.parse("x", {"steps": [{"tap": {"desc": "whatever"}}]})}
    assert scan.check_recipes(recipes, scan.scan(cfg)) == []
