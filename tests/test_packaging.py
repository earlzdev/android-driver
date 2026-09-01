"""Guards on the files that decide which code a user actually runs.

None of this is exercised by the rest of the suite: every other test imports
`android_driver` straight from the working tree, so a launcher that serves a
months-old build still passes them all.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_MCP = ROOT / "mcp-config.json"
DEV_MCP = ROOT / ".mcp.json"
MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"


def servers(path: Path) -> dict:
    return json.loads(path.read_text())["mcpServers"]


def only_server(path: Path) -> dict:
    entries = list(servers(path).values())
    assert len(entries) == 1, f"{path.name} should declare exactly one server"
    return entries[0]


@pytest.mark.parametrize("path", [PLUGIN_MCP, DEV_MCP], ids=["plugin", "dev"])
def test_launcher_rebuilds_when_sources_change(path: Path) -> None:
    """Never launch with `uvx --from <path>`.

    uv keys that build cache on `pyproject.toml`'s mtime, so editing anything
    under `src/` leaves the cached wheel in place and the server keeps serving
    the old code — silently, with no warning and a plausible-looking startup.
    A plugin update that ships code without bumping the version never takes
    effect at all. `uv run` re-syncs from the source tree every start.
    """
    entry = only_server(path)
    argv = [entry["command"], *entry.get("args", [])]
    assert entry["command"] != "uvx", f"{path.name}: uvx serves a stale build; use `uv run`"
    assert "--from" not in argv, f"{path.name}: `--from` implies the uvx build cache"
    assert argv[:2] == ["uv", "run"], f"{path.name}: expected `uv run`, got {argv}"


def test_plugin_server_is_pinned_to_the_plugin_and_points_at_the_user_project() -> None:
    """The two roots differ: code comes from the plugin, config from the project.

    Resolving either one by cwd instead puts the server in whichever directory
    the client happened to launch it from.
    """
    entry = only_server(PLUGIN_MCP)
    argv = entry["args"]
    assert "${CLAUDE_PLUGIN_ROOT}" in argv, "the project to run must be the plugin's own root"
    assert entry["env"]["ANDROID_DRIVER_PROJECT"] == "${CLAUDE_PROJECT_DIR}"


def test_dev_server_name_does_not_collide_with_the_installed_plugin() -> None:
    """Two servers sharing a name makes it ambiguous which one a tool call reaches."""
    assert set(servers(DEV_MCP)) == {"android-driver-dev"}
    assert set(servers(PLUGIN_MCP)) == {"android-driver"}


def test_manifest_references_the_mcp_config_that_exists() -> None:
    manifest = json.loads(MANIFEST.read_text())
    referenced = ROOT / manifest["mcpServers"].removeprefix("./")
    assert referenced.resolve() == PLUGIN_MCP.resolve()


def test_plugin_and_package_versions_agree() -> None:
    """A user's install path is keyed on the plugin version; skew makes updates hard to reason about."""
    manifest = json.loads(MANIFEST.read_text())
    pyproject = (ROOT / "pyproject.toml").read_text()
    version = next(
        line.split("=", 1)[1].strip().strip('"')
        for line in pyproject.splitlines()
        if line.startswith("version =")
    )
    assert manifest["version"] == version


def test_marketplace_lists_this_plugin() -> None:
    entries = json.loads(MARKETPLACE.read_text())["plugins"]
    manifest = json.loads(MANIFEST.read_text())
    assert [p["name"] for p in entries] == [manifest["name"]]
