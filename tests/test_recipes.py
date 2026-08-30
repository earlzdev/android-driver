"""The recipe engine: parsing, interpolation, execution, retry and failure reporting."""

from __future__ import annotations

import pytest

from android_driver import recipes as R
from android_driver.run import Runs

LOGIN = {
    "description": "Sign in",
    "params": {
        "email": {"required": True},
        "password": {"required": True, "secret": True},
        "wait": {"type": "int", "default": 20},
    },
    "steps": [
        {"type": {"desc": "text_field_Email", "text": "{{email}}"}},
        {"type": {"desc": "text_field_Password", "text": "{{password}}"}},
        {"tap": {"desc": "login_button"}},
    ],
}


@pytest.fixture
def runner(session, cfg):
    return R.Runner(R.Context(session, cfg, Runs(cfg)), {})


# ── parsing ───────────────────────────────────────────────────────────────────


def test_parses_params_and_steps():
    recipe = R.parse("login", LOGIN)
    assert [p.name for p in recipe.params] == ["email", "password", "wait"]
    assert recipe.param_map["wait"].type == "int" and recipe.param_map["wait"].required is False
    assert recipe.param_map["email"].required is True
    assert [s.verb for s in recipe.steps] == ["type", "type", "tap"]


def test_shorthands():
    steps = [{"launch": None}, {"sleep": 2}, {"press": "back"}, {"tap": "OK"}, "screenshot"]
    recipe = R.parse("smoke", steps)
    assert [s.args for s in recipe.steps] == [{}, {"seconds": 2}, {"key": "back"}, {"text": "OK"}, {}]


def test_param_list_shorthand_makes_them_required():
    recipe = R.parse("x", {"params": ["room"], "steps": [{"sleep": 1}]})
    assert recipe.params[0].required is True


def test_step_options_are_accepted_inside_the_verb_mapping():
    """`retry` beside `timeout_s` is the natural way to write it, and must work.

    Leaking it through as a verb argument fails at runtime with a signature error
    and, worse, silently drops the retry the recipe author asked for.
    """
    step = R.parse("x", {"steps": [{"expect_visible": {"desc": "d", "timeout_s": 15, "retry": 2}}]}).steps[0]
    assert step.retry == 2
    assert step.args == {"desc": "d", "timeout_s": 15}


def test_step_options_outside_the_mapping_win_over_inside():
    step = R.parse("x", {"steps": [{"tap": {"text": "OK", "retry": 1}, "retry": 9}]}).steps[0]
    assert step.retry == 9 and step.args == {"text": "OK"}


def test_step_meta_is_not_mistaken_for_a_verb():
    step = R.parse("x", {"steps": [{"tap": "OK", "retry": 2, "optional": True, "label": "confirm"}]}).steps[0]
    assert (step.verb, step.retry, step.optional, step.name) == ("tap", 2, True, "confirm")


@pytest.mark.parametrize(
    "spec, message",
    [
        ({"steps": [{"tap": {}, "swipe": {}}]}, "exactly one verb"),
        ({"steps": [{"teleport": {}}]}, "unknown step"),
        ({"steps": []}, "no steps"),
        ({"steps": [{"sleep": 1}], "on_failure": "panic"}, "on_failure must be"),
        ({"steps": [{"sleep": 1}], "extra": 1}, "unknown key"),
        ({"params": {"x": {"type": "date"}}, "steps": [{"sleep": 1}]}, "use one of"),
    ],
)
def test_malformed_recipes_are_rejected(spec, message):
    with pytest.raises(R.RecipeError, match=message):
        R.parse("x", spec)


def test_bad_recipe_names_are_rejected():
    with pytest.raises(R.RecipeError, match="to be usable as a tool name"):
        R.parse("Log In", {"steps": [{"sleep": 1}]})


def test_load_all_skips_the_broken_one_and_keeps_the_rest(cfg):
    cfg.recipes = {"good": [{"sleep": 1}], "bad": {"steps": [{"nope": {}}]}}
    assert sorted(R.load_all(cfg)) == ["good"]


# ── interpolation ─────────────────────────────────────────────────────────────


def test_interpolation_substitutes_and_preserves_types():
    args = {"text": "hello {{name}}", "timeout_s": "{{wait}}", "nested": {"list": ["{{name}}"]}}
    out = R.interpolate(args, {"name": "ann", "wait": 30})
    assert out == {"text": "hello ann", "timeout_s": 30, "nested": {"list": ["ann"]}}
    assert isinstance(out["timeout_s"], int)


def test_unknown_placeholder_names_the_available_ones():
    with pytest.raises(R.StepFailed, match="Available: \\['known'\\]"):
        R.interpolate("{{typo}}", {"known": 1})


# ── execution ─────────────────────────────────────────────────────────────────


def test_runs_every_step_against_the_device(runner, driver):
    result = runner.run(R.parse("login", LOGIN), {"email": "a@b.c", "password": "hunter2"})
    assert result["ok"] is True
    assert [s["status"] for s in result["steps"]] == ["ok", "ok", "ok"]
    assert ("set_text", "text_field_Email", "a@b.c") in driver.calls
    assert ("click", 540, 1440) in driver.calls


def test_secrets_are_redacted_in_the_result(runner):
    result = runner.run(R.parse("login", LOGIN), {"email": "a@b.c", "password": "hunter2"})
    assert result["params"] == {"email": "a@b.c", "password": "***", "wait": 20}


def test_missing_required_parameter_is_refused(runner):
    with pytest.raises(R.StepFailed, match="requires the 'password' parameter"):
        runner.run(R.parse("login", LOGIN), {"email": "a@b.c"})


def test_unknown_parameter_is_refused(runner):
    with pytest.raises(R.StepFailed, match="unknown parameter"):
        runner.run(R.parse("login", LOGIN), {"email": "a", "password": "b", "extra": 1})


def test_failure_stops_the_flow_and_reports_the_step(runner):
    recipe = R.parse("x", {"steps": [{"tap": {"desc": "nope"}}, {"sleep": 5}]})
    result = runner.run(recipe, {})
    assert result["ok"] is False
    assert result["failed_step"]["index"] == 1
    assert "step 1 (`tap`) failed" in result["error"]
    assert len(result["steps"]) == 1  # the sleep never ran


def test_on_failure_continue_runs_the_rest(runner):
    recipe = R.parse("x", {"on_failure": "continue", "steps": [{"tap": {"desc": "nope"}}, {"press": "back"}]})
    result = runner.run(recipe, {})
    assert result["ok"] is False
    assert [s["status"] for s in result["steps"]] == ["failed", "ok"]


def test_optional_step_does_not_fail_the_recipe(runner):
    recipe = R.parse("x", {"steps": [{"tap": {"desc": "nope"}, "optional": True}, {"press": "back"}]})
    result = runner.run(recipe, {})
    assert result["ok"] is True
    assert [s["status"] for s in result["steps"]] == ["skipped", "ok"]


def test_retry_reattempts_until_the_screen_catches_up(runner, driver):
    calls = {"n": 0}
    original = driver.dump_hierarchy

    def flaky():
        calls["n"] += 1
        if calls["n"] > 2:
            driver.advance("home_screen")
        return original()

    driver.dump_hierarchy = flaky
    recipe = R.parse("x", {"steps": [{"tap": {"desc": "logout_button"}, "retry": 3}]})
    assert runner.run(recipe, {})["ok"] is True


def test_failed_step_captures_evidence(runner, tmp_path):
    result = runner.run(R.parse("x", {"steps": [{"tap": {"desc": "nope"}}]}), {})
    failed = result["failed_step"]
    assert failed["screenshot"].endswith(".png")
    assert failed["hierarchy"].endswith(".xml")
    assert "login_button" in open(failed["hierarchy"]).read()


def test_a_wrong_argument_name_is_reported_as_config(runner):
    result = runner.run(R.parse("x", {"steps": [{"press": {"keycode": "back"}}]}), {})
    assert "does not accept those arguments" in result["failed_step"]["error"]


def test_expect_failure_becomes_a_step_failure(runner):
    recipe = R.parse("x", {"steps": [{"expect_visible": {"text": "Welcome", "timeout_s": 0.1}}]})
    result = runner.run(recipe, {})
    assert result["ok"] is False
    assert "did not" in result["error"] or "appeared" in result["error"]
    assert "login_button" in result["failed_step"]["screen"]


def test_nested_recipes_run_and_propagate_failure(session, cfg):
    registry = {
        "inner": R.parse("inner", {"steps": [{"press": "back"}]}),
        "broken": R.parse("broken", {"steps": [{"tap": {"desc": "nope"}}]}),
    }
    runner = R.Runner(R.Context(session, cfg, Runs(cfg)), registry)
    outer = R.parse("outer", {"steps": [{"run": "inner"}]})
    assert runner.run(outer, {})["ok"] is True
    failing = R.parse("outer", {"steps": [{"run": "broken"}]})
    assert runner.run(failing, {})["ok"] is False
    unknown = R.parse("outer", {"steps": [{"run": "ghost"}]})
    assert "no recipe named 'ghost'" in runner.run(unknown, {})["failed_step"]["error"]


def test_recursion_is_bounded(session, cfg):
    registry = {"loop": R.parse("loop", {"steps": [{"run": "loop"}]})}
    runner = R.Runner(R.Context(session, cfg, Runs(cfg)), registry)
    assert "nesting deeper than" in runner.run(registry["loop"], {})["failed_step"]["error"]


def test_id_is_translated_to_the_action_layer_name(runner, driver):
    recipe = R.parse("x", {"steps": [{"tap": {"id": "login_button"}}]})
    assert runner.run(recipe, {})["ok"] is True
    assert ("click", 540, 1440) in driver.calls


# ── tool generation ───────────────────────────────────────────────────────────


def test_build_tool_signature_matches_the_params():
    import inspect

    tool = R.build_tool(R.parse("login", LOGIN), lambda: None)
    params = inspect.signature(tool).parameters
    assert list(params) == ["email", "password", "wait"]
    assert params["email"].default is inspect.Parameter.empty
    assert params["wait"].default == 20
    assert tool.__name__ == "login"
    assert "Sign in" in tool.__doc__


def test_build_tool_reports_binding_errors_as_a_result(session, cfg):
    recipe = R.parse("login", LOGIN)
    factory = lambda: R.Runner(R.Context(session, cfg, Runs(cfg)), {})  # noqa: E731
    result = R.build_tool(recipe, factory)(email="a@b.c")
    assert result["ok"] is False and "requires the 'password' parameter" in result["error"]
