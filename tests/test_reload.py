"""Reloading config at runtime, and finding a config that is not at the project root."""

from __future__ import annotations

import pytest

from android_driver import config as config_mod
from android_driver import server
from android_driver.run import Runs

CONFIG = """
app:
  package: com.example.{name}
recipes:
  {name}_flow:
    steps:
      - press: back
"""


@pytest.fixture
def wired(monkeypatch, cfg, session):
    monkeypatch.setattr("android_driver.run.adb.device_info", lambda serial: {"serial": serial})
    monkeypatch.setattr("android_driver.run.adb.logcat_clear", lambda serial: None)
    monkeypatch.setattr("android_driver.run.adb.logcat_dump", lambda serial, **kw: [])
    monkeypatch.setattr(server, "CFG", cfg)
    monkeypatch.setattr(server, "SESSION", session)
    monkeypatch.setattr(server, "RUNS", Runs(cfg))
    monkeypatch.setattr(server, "RECIPES", {})
    monkeypatch.setattr(server, "_RECIPE_TOOLS", [])
    yield
    for name in list(server._RECIPE_TOOLS):
        server.mcp._tool_manager._tools.pop(name, None)


# ── discovery ─────────────────────────────────────────────────────────────────


def test_a_config_one_level_down_is_found(tmp_path, monkeypatch):
    """A repo whose app lives in a subdirectory is ordinary, not an error."""
    (tmp_path / "test_app").mkdir()
    (tmp_path / "test_app" / ".android-driver.yaml").write_text(CONFIG.format(name="app"))
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(tmp_path))
    assert config_mod.find_config_file() == tmp_path / "test_app" / ".android-driver.yaml"
    assert config_mod.load().app.package == "com.example.app"


def test_a_config_at_the_root_still_wins(tmp_path, monkeypatch):
    (tmp_path / ".android-driver.yaml").write_text(CONFIG.format(name="root"))
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / ".android-driver.yaml").write_text(CONFIG.format(name="nested"))
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(tmp_path))
    assert config_mod.load().app.package == "com.example.root"


def test_two_configs_below_and_none_above_is_refused_not_guessed(tmp_path, monkeypatch):
    for name in ("alpha", "beta"):
        (tmp_path / name).mkdir()
        (tmp_path / name / ".android-driver.yaml").write_text(CONFIG.format(name=name))
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(tmp_path))
    assert config_mod.find_config_file() is None


def test_build_output_is_not_searched(tmp_path, monkeypatch):
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / ".android-driver.yaml").write_text(CONFIG.format(name="stale"))
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(tmp_path))
    assert config_mod.find_config_file() is None


# ── reload ────────────────────────────────────────────────────────────────────


def test_reload_picks_up_a_new_config_and_its_recipes(wired, tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(tmp_path))
    (tmp_path / ".android-driver.yaml").write_text(CONFIG.format(name="first"))

    result = server.reload_config()
    assert result["ok"] is True
    assert result["package"] == "com.example.first"
    assert result["recipe_tools"] == ["first_flow"]
    assert server.CFG.app.package == "com.example.first"


def test_reload_replaces_stale_recipe_tools_rather_than_shadowing_them(wired, tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(tmp_path))
    path = tmp_path / ".android-driver.yaml"

    path.write_text("app:\n  package: com.x\nrecipes:\n  flow:\n    steps:\n      - press: back\n")
    server.reload_config()
    assert server.RECIPES["flow"].steps[0].verb == "press"

    path.write_text("app:\n  package: com.x\nrecipes:\n  flow:\n    steps:\n      - swipe: {}\n")
    server.reload_config()
    # FastMCP's add_tool keeps the incumbent on a name clash, so the old tool must
    # be retired first or the recipe stays frozen at its startup definition.
    assert server.RECIPES["flow"].steps[0].verb == "swipe"
    tool = server.mcp._tool_manager._tools["flow"]
    assert "swipe" in tool.description


def test_reload_keeps_the_selected_device(wired, tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(tmp_path))
    (tmp_path / ".android-driver.yaml").write_text(CONFIG.format(name="keep"))
    monkeypatch.setattr("android_driver.adb.list_serials", lambda: ["emulator-test"])
    assert server.reload_config()["device"] == "emulator-test"


def test_reload_refuses_while_a_run_is_open(wired, tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(tmp_path))
    server.run_start("busy")
    result = server.reload_config()
    assert result["ok"] is False and "run_end" in result["error"]
