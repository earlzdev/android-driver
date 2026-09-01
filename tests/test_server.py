"""The tool surface: shapes, evidence on failure, and recipe registration."""

from __future__ import annotations

import asyncio

from android_driver import server


def tool_names() -> set[str]:
    return {t.name for t in asyncio.run(server.mcp.list_tools())}


def test_every_documented_tool_is_registered():
    assert set(server.RESERVED_TOOL_NAMES) <= tool_names()


def test_success_returns_ok_and_the_payload(wired, driver):
    result = server.tap(desc="login_button")
    assert result == {"ok": True, "tapped": "Sign in", "at": [540, 1440]}
    assert ("click", 540, 1440) in driver.calls


def test_failure_returns_the_error_and_captures_evidence(wired):
    result = server.tap(desc="nope")
    assert result["ok"] is False
    assert "no element matches" in result["error"]
    assert result["screenshot"].endswith(".png") and result["hierarchy"].endswith(".xml")


def test_actions_are_recorded_on_the_open_run(wired, session):
    server.run_start("smoke")
    server.tap(desc="login_button")
    server.tap(desc="nope")
    assert [(e.tool, e.status) for e in wired.current.events] == [
        ("run_start", "ok"),
        ("tap", "ok"),
        ("tap", "failed"),
    ]


def test_assertions_keep_their_passed_flag(wired):
    assert server.expect_visible(desc="login_button", timeout_s=1)["passed"] is True
    failed = server.expect_visible(text="Welcome", timeout_s=0.1)
    assert failed["ok"] is False and failed["passed"] is False


def test_screen_renders_the_index(wired):
    out = server.screen()
    assert out.startswith("device=emulator-test app=com.example.app/.LoginActivity")
    assert 'desc=login_button' in out


def test_read_tools_return_errors_as_text_not_exceptions(wired, driver):
    driver.dump_hierarchy = lambda: (_ for _ in ()).throw(RuntimeError("device offline"))
    assert server.screen().startswith("error: RuntimeError")
    assert server.dump_ui_xml().startswith("error: RuntimeError")


def test_run_recipe_reports_an_unknown_name(wired):
    result = server.run_recipe("ghost")
    assert result["ok"] is False and "no recipe named 'ghost'" in result["error"]


def test_recipes_become_tools_with_typed_parameters(monkeypatch, cfg):
    cfg.recipes = {
        "login": {"params": {"email": {"required": True}}, "steps": [{"tap": {"desc": "login_button"}}]}
    }
    monkeypatch.setattr(server, "CFG", cfg)
    registered = server.register_recipes()
    try:
        assert registered == ["login"]
        tool = [t for t in asyncio.run(server.mcp.list_tools()) if t.name == "login"][0]
        assert tool.inputSchema["required"] == ["email"]
    finally:
        server.mcp._tool_manager._tools.pop("login", None)


def test_a_recipe_named_after_a_builtin_gets_a_prefix(monkeypatch, cfg):
    cfg.recipes = {"screenshot": [{"press": "back"}]}
    monkeypatch.setattr(server, "CFG", cfg)
    registered = server.register_recipes()
    try:
        assert registered == ["recipe_screenshot"]
        assert "screenshot" in tool_names()  # the built-in survived
    finally:
        server.mcp._tool_manager._tools.pop("recipe_screenshot", None)
