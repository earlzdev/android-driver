# Contributing

Bug reports, recipes for apps you have driven, and backend fixes are all welcome. The project is
early, so the shape of things is still open to argument.

## Setup

```bash
git clone https://github.com/earlzdev/android-driver.git
cd android-driver
uv sync --extra dev
```

```bash
uv run pytest                     # 129 unit tests, no device needed
uv run ruff check src tests
```

The unit suite runs against a fake driver over recorded hierarchy fixtures in `tests/fixtures/`, so
the whole engine — selector resolution, recipes, assertions, run bundles, config discovery — is
testable without an emulator. Please keep it that way: a test that needs a device belongs in
`tests/integration/`.

## Working on the server from Claude Code

Opening this repo in Claude Code gives you the tools built from your working tree, via a
project-scoped `.mcp.json`. Edit the source, restart the server, and the change is live.

Two things about that setup are load-bearing:

- The dev server is named `android-driver-dev`, not `android-driver`. If you also have the plugin
  installed, two servers sharing a name makes it ambiguous which one a tool call reaches.
- The plugin's own MCP config is a separate file, `mcp-config.json`. A `.mcp.json` at a repo root is
  read as a *project* config, where `${CLAUDE_PLUGIN_ROOT}` does not resolve.

**Never launch with `uvx --from <path>`.** uv keys that build cache on `pyproject.toml`'s mtime, so
editing anything under `src/` leaves the cached wheel in place and the server keeps serving old code
— silently, with a normal-looking startup. `uv run` re-syncs from source every start.
`tests/test_packaging.py` will fail if anyone reintroduces it, because nothing else would catch it.

## The live suite

Needs a booted emulator, and is skipped otherwise:

```bash
ANDROID_DRIVER_LIVE=1 uv run pytest tests/integration
```

It drives [FlakyDemo](test_app/), the demo app in this repo. Build and install it first:

```bash
cd test_app && ./gradlew :app:assembleDebug
```

The live suite saves and loads snapshots and can leave the device in an unexpected state, so point it
at a scratch AVD rather than one you care about.

## Testing a change end to end

Unit tests cannot see the two things most likely to break for a user: what the *shipped* launcher
runs, and what a real device does. Both have burned this project before. If you touch packaging,
`session.py`, `emulator.py` or the drivers, run the loop for real against FlakyDemo — install, smoke,
and one repro from a snapshot — before opening the PR.

## Style

- Comments explain **why**, not what. If a line is there because of a device quirk, say which quirk —
  that is the knowledge worth keeping.
- Errors should say what to do next. This is the standard to match:

  ```
  no adb device in state 'device'. Start an emulator with `start_emulator`,
  or check `adb devices` for an unauthorized/offline entry.
  ```

- Tool docstrings are read by an agent, not just by you. Write them for the reader who has to decide
  whether this is the right tool.
- `ruff check` must pass. The project does not enforce `ruff format`.

## Adding a tool

Tools live in `src/android_driver/server.py` and are thin: they wrap a function from `actions.py` or
`expect.py` in `_act`, which handles errors, timing, run recording and evidence capture. Put real
logic in the action layer, so recipes get it too — recipes and hand-driven tools share that path
deliberately, and a tool that bypasses it will drift.

Add the name to `RESERVED_TOOL_NAMES`, and a row to the tool table in `README.md`.

## Pull requests

Say what broke and how you know it is fixed. A failing test that now passes is the best form of that;
a run directory from a real device is a good second.
