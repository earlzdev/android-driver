# android_driver

An MCP server that turns an Android emulator into a **deterministic, agent-drivable test harness**.

Most Android MCP servers are adb wrappers: tap, swipe, screenshot, dump XML. This one is built for the
loop an AI agent actually needs to run — *build → install → drive → assert → reset → repeat* — and it
is opinionated about the four things that make that loop work:

**1. Snapshots, so a repro is actually reproducible.** `snapshot_save` freezes the emulator's exact
state; `snapshot_load` restores it in a couple of seconds (measured: 1.3s on a Pixel 7 AVD).
Reinstalling the app and navigating back to the starting screen costs 30–90s and drifts. An agent
testing thirty variations of a bug hypothesis needs the cheap, identical option.

**2. A screen index instead of a wall of XML.** A raw `uiautomator dump` is 50–200 KB per screen —
tens of thousands of tokens for a model that just wants to know what it can tap. `screen` returns:

```
device=emulator-5554 app=com.android.settings/.Settings screen=1080x2400 driver=uiautomator2
#5 [Scroll] id=settings_homepage_container (scrollable) @(540,1236)
#6 [Image] desc="Profile picture, double tap to open Google Account" id=account_avatar @(954,346)
#7 [Text] "Settings" id=homepage_title @(235,472)
```

Then `tap(ref="#7")`. Two orders of magnitude smaller, and it reads like a menu. The raw tree is still
there behind `dump_ui_xml` for when you genuinely need it.

**3. Assertions that collect their own evidence.** `expect_visible` polls, so it is safe right after a
tap and will not flake on an animation; when it fails it hands back the screen index that *was* there,
plus a screenshot and a hierarchy dump on disk. `expect_no_crash` reads the `crash` buffer as well as
`main`, because a native abort never reaches `main` at all. Wrap a sequence in `run_start` /
`run_end` and you get `runs/<id>/` with a timeline, a report, the logcat slice for exactly that
window, and every failure artifact — so an agent can cite a directory instead of describing what it
saw.

**4. Your flows as first-class tools.** Six steps that every test starts with — sign in, create an
order, join a call — go in `.android-driver.yaml` once and become real MCP tools with typed parameters.
An agent sees `login(email, password)` in its tool list rather than rediscovering the flow from a
screen dump every session. Recipes call the same code path as the hand-driven tools, so the two
cannot drift apart.

Plus the device knowledge that costs an afternoon each to learn: uninstall-then-install instead of
`pm install -r` (different debug keys across branches otherwise fail with
`INSTALL_FAILED_UPDATE_INCOMPATIBLE`); checking `mInputShown` before pressing Back, so dismissing the
keyboard never dismisses the dialog behind it; writing to Compose `TextField`s through the
accessibility node rather than tap-then-type, which lands text in the wrong field; a post-click settle
before the next query; an `appops` pass for OEM permission overlays that keep blocking after
`pm grant` reports success.

## Install

It is a Claude Code plugin: one install brings the tools, a skill that teaches Claude the testing
loop, and three slash commands.

```bash
claude plugin marketplace add earlzdev/android-driver
claude plugin install android-driver@android-driver
```

That is all — the plugin builds the Python server on demand with `uvx`, so there is no venv to manage
and nothing to reinstall when it updates. It also passes your project directory to the server, so
`.android-driver.yaml` is found no matter where Claude was launched from.

**Or as a plain MCP server**, if you would rather not install a plugin:

```bash
git clone https://github.com/earlzdev/android-driver.git ~/src/android-driver
claude mcp add android-driver -- uvx --from ~/src/android-driver android-driver
```

Run that from the project you want to test, and add `-s user` to register it for every project. Note
that the standalone route discovers `.android-driver.yaml` by walking up from the directory the server
was launched in, so a launcher that changes the working directory (notably `uv run --directory`)
breaks discovery silently — you get the generic tools and none of your recipes. Set
`ANDROID_DRIVER_PROJECT=/path/to/your/project` in that case. The startup line on stderr always says
which config it loaded.

Requirements: `adb` on `PATH`, the Android SDK's `emulator` binary, Python ≥ 3.10. For the faster
uiautomator2 backend, run `python -m uiautomator2 init` once per device; without it the server falls
back to a pure-adb backend that needs nothing installed on the device.

## What the plugin adds

| | |
|---|---|
| `/android-driver:setup` | Detects your `applicationId`, build command and UI toolkit, writes a starter `.android-driver.yaml`, boots an emulator and proves the loop works |
| `/android-driver:repro` | Reproduces a bug by varying one thing at a time from a snapshot, and hands back a run directory as evidence |
| `/android-driver:smoke` | Build, install, walk the main flows, assert nothing crashed |
| `android-testing` skill | Loads automatically when Claude is driving the app, so it reaches for `screen` over raw XML and snapshots over slow resets without being told |

## Configure

Optional. Drop `.android-driver.yaml` at your project root — the server finds it by walking up from the
working directory. Without one, every generic tool still works; you just pass the package name
explicitly and cannot use `build_app` or recipes. Full examples for a Compose app and a View-system
app are in [`examples/`](examples/).

```yaml
app:
  package: com.example.myapp
  activity: .MainActivity          # optional; the launcher intent is resolved otherwise

build:
  command: ./gradlew :app:assembleDebug
  apk_glob: app/build/outputs/apk/debug/*.apk

install:
  strategy: uninstall-then-install  # or: reinstall
  grant_runtime_perms: true
  appops: [CAMERA, RECORD_AUDIO]    # OEM overlay workarounds

timing:
  cold_start_settle_s: 2.0
  click_settle_s: 0.25

driver:
  backend: auto                     # auto | uiautomator2 | adb

selectors:                          # scanned so a typo is a warning, not a mystery
  sources: ["app/src/main/**/*.kt"]

recipes:
  login:
    description: Sign in and land on the home screen
    params:
      email: {required: true}
      password: {required: true, secret: true}
    steps:
      - launch:
      - type: {desc: text_field_Email, text: "{{email}}"}
      - type: {desc: text_field_Password, text: "{{password}}"}
      - tap: {desc: login_button}
      - expect_visible: {desc: home_greeting, timeout_s: 20}
```

## Tools

44 of them, plus one per configured recipe.

| Group | Tools |
|---|---|
| Emulator | `list_avds` `start_emulator` `stop_emulator` `wait_for_boot` `snapshot_save` `snapshot_load` `snapshot_list` `snapshot_delete` |
| Device | `list_devices` `select_device` `device_info` |
| App | `build_app` `install_app` `uninstall_app` `app_info` `launch_app` `force_stop` `clear_app_data` |
| UI | `screen` `tap` `tap_xy` `long_press` `type_text` `swipe` `scroll_to` `press_key` `screenshot` `dump_ui_xml` |
| Assertions | `expect_visible` `expect_gone` `expect_log` `expect_no_crash` |
| Runs | `run_start` `run_end` `run_list` `record_start` `record_stop` |
| Recipes | `list_recipes` `run_recipe` `check_recipes` `list_selectors` |
| Logs | `logcat_clear` `logcat_read` |
| Shell | `shell` |

`shell` is unrestricted on purpose — this is a development tool, not a sandbox. It can wipe device
data, kill processes and read files. Point it at emulators and test devices, not at anything you care
about.

## The loop

```
start_emulator(avd="Pixel_7")   # reuses it if already running
install_app(build_first=True)
launch_app()
snapshot_save("clean")          # ← the state every attempt returns to
run_start("issue 412: crash on empty search")
  … tap / type / expect_visible …
  expect_no_crash()
run_end()                       # → runs/<id>/report.md
snapshot_load("clean")          # next variation, from identical state
```

[`docs/agent-guide.md`](docs/agent-guide.md) is a `CLAUDE.md` fragment you can drop into a project so
an agent picks this up without being told.

## Recipes

Each recipe in your config is registered as its own MCP tool with typed parameters, and is also
reachable through the generic `run_recipe(name, params)`.

Steps: `tap` `tap_xy` `long_press` `type` `swipe` `scroll_to` `press` `screenshot` · `build` `install`
`uninstall` `launch` `force_stop` `clear_data` · `snapshot_save` `snapshot_load` · `expect_visible`
`expect_gone` `expect_log` `expect_no_crash` · `sleep` `shell` `logcat_clear` `run`.

`{{param}}` interpolates anywhere in a step's arguments and keeps its type. Per step: `retry: 2`
re-attempts against a freshly read screen, `optional: true` lets it fail without failing the flow,
`settle_s` waits afterwards, `label` renames it in the report — written either beside the verb or
inside its argument mapping, whichever reads better. Per recipe: `on_failure: continue`.
`- run: {recipe: other}` composes them. Parameters marked `secret: true` are redacted from logs and
reports.

`list_selectors` shows the `testTag` / `contentDescription` / `android:id` / string-resource literals
the project's own sources declare, and `check_recipes` cross-checks every recipe against them — so a
rename shows up as a warning rather than as "element not found" three steps into a flow. See
[`examples/README.md`](examples/README.md) for the full syntax.

## Development

```bash
uv sync --extra dev
uv run pytest              # 104 unit tests, no device needed
uv run ruff check src tests
```

The repo ships a project-scoped `.mcp.json` that runs the server straight from your checkout, so
opening this directory in Claude Code gives you the tools built from your working tree — edit the
source, restart the server, and the change is live. The plugin's own MCP config is a separate file,
`mcp-config.json`, precisely so it does not collide with that: `.mcp.json` at a repo root is read as a
project config, where `${CLAUDE_PLUGIN_ROOT}` does not resolve.

The unit suite runs against a fake driver over recorded hierarchy fixtures. The live suite needs a
booted emulator and is skipped otherwise:

```bash
ANDROID_DRIVER_LIVE=1 uv run pytest tests/integration
```

## Status

Early but working end to end. Emulator lifecycle, snapshots, both driver backends, the screen index,
assertions, run bundles, screen recording, recipes and selector scanning are all implemented and
covered by tests; the live suite passes against a Pixel 7 AVD. Packaged as a Claude Code plugin with a
skill and three commands.

Not published to PyPI yet — the plugin builds from source, so it does not need to be. See
[docs/roadmap.md](docs/roadmap.md).

## License

MIT
