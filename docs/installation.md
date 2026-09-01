# Installation

## Requirements

| | |
|---|---|
| `adb` | On `PATH`. Ships with the Android SDK platform-tools. |
| `emulator` | On `PATH` if you want android-driver to boot AVDs for you. Not needed if you start them yourself or drive real hardware. |
| Python | ≥ 3.10. |
| `uv` | Used to launch the server. [Install it](https://docs.astral.sh/uv/getting-started/installation/) if you do not have it. |

For the uiautomator2 backend, run `python -m uiautomator2 init` once per device. Without it the
server falls back to a pure-adb backend that needs nothing installed on the device — slower, and
unable to fill a Compose `TextField` reliably, but it works anywhere.

## As a Claude Code plugin (recommended)

```bash
claude plugin marketplace add earlzdev/android-driver
claude plugin install android-driver@android-driver
```

This brings the 45 tools, the `android-testing` skill, and the `/android-driver:setup`,
`/android-driver:smoke` and `/android-driver:repro` commands.

The plugin sets `ANDROID_DRIVER_PROJECT` to your project directory, so your `.android-driver.yaml`
is found regardless of where Claude Code was started from.

To pick up a new version:

```bash
claude plugin update android-driver@android-driver
```

## As a plain MCP server

If you would rather not install a plugin — or you are using a different MCP client:

```bash
git clone https://github.com/earlzdev/android-driver.git ~/src/android-driver

claude mcp add android-driver \
  -e ANDROID_DRIVER_PROJECT="$PWD" \
  -- uv run --project ~/src/android-driver android-driver
```

Run that from the project you want to test. Add `-s user` to register it for every project.

You get the tools, but not the skill or the slash commands — those are plugin components. If you
want an agent to pick up the workflow anyway, drop [`agent-guide.md`](agent-guide.md) into your
project's `CLAUDE.md`.

For any other MCP client, the equivalent config is:

```json
{
  "mcpServers": {
    "android-driver": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/android-driver", "android-driver"],
      "env": { "ANDROID_DRIVER_PROJECT": "/path/to/your/android/project" }
    }
  }
}
```

## How the config is found

In order:

1. `ANDROID_DRIVER_PROJECT` if set — this is what the plugin uses, and it makes discovery
   independent of the working directory.
2. Otherwise, walking **up** from the current directory.
3. Failing that, up to three levels **down**, skipping build output. A repo whose Android app lives
   in `app/`, `android/` or `test_app/` is completely ordinary, and this is what makes it work
   without configuration.

Two configs below and none above is **refused rather than guessed at** — set
`ANDROID_DRIVER_PROJECT` to say which one you mean.

Accepted filenames: `.android-driver.yaml`, `.android-driver.yml`, `android-driver.yaml`,
`android-driver.yml`.

The server prints which config it loaded to stderr on startup:

```
[config] loaded /path/to/project/.android-driver.yaml (package=com.example.app, recipes=11)
```

`reload_config` re-reads the file without a reconnect, and re-registers recipe tools.

## Troubleshooting

**"No app package configured" and none of my recipes are there.**
The server did not find your config. Check the startup line on stderr — if it says
`no config file found; using defaults`, set `ANDROID_DRIVER_PROJECT` explicitly.

**My changes to the config do nothing.**
Call `reload_config`. The config is read at startup.

**My changes to the *source* do nothing** (contributors only).
Do not launch with `uvx --from <path>`. uv keys that build cache on `pyproject.toml`'s mtime, so
editing anything under `src/` leaves the cached wheel in place and the server keeps serving old code
— silently, with a normal-looking startup. Use `uv run`, which re-syncs from source each start. Both
shipped configs already do.

**`RemoteDisconnected` or `device offline` right after a snapshot restore.**
Fixed — `snapshot_load` now waits for the device to come back. If you see it on an older version,
update.

**Timestamps in my run report are in the past.**
Expected. Restoring a snapshot rewinds the emulator's clock to the moment the snapshot was saved.
Compare log timestamps to each other, not to your watch.

**`uiautomator2` is not being used.**
Run `python -m uiautomator2 init`. The `auto` backend falls back to adb silently; the startup line
on stderr says which one won.
