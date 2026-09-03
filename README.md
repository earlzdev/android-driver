# android-driver

**Drive an Android emulator as a deterministic test harness — from Claude Code.**

[![CI](https://github.com/earlzdev/android-driver/actions/workflows/ci.yml/badge.svg)](https://github.com/earlzdev/android-driver/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

You ask an agent to reproduce a bug in your Android app. It dumps 80 KB of accessibility XML into its
own context, taps something that turns out to be the wrong element, and when the bug does not appear
it cannot repeat what it just did — because the app is now three screens deep in a state nobody
recorded.

android-driver is built for that loop instead: **build → install → drive → assert → reset → repeat.**

```
> reproduce the crash when the bio field goes over 100 characters

  snapshot_load("clean")                          1.9s
  open_settings()                                 ok
  type_text(id=text_field_Bio, text=110 chars)    ok
  expect_log("StringIndexOutOfBoundsException")   ok — matched
  expect_no_crash()                               FAILED — 1 crash record

  runs/20260901-080304-repro-set-06/report.md
  → java.lang.StringIndexOutOfBoundsException: begin 0, end 120, length 110
      at ...screens.SettingsScreenKt.SettingsScreen$textFields(SettingsScreen.kt:149)
```

Three attempts from the same snapshot, three identical results, and a directory of evidence to point
at. That is the whole idea.

---

## Install

It is a Claude Code plugin: one install brings the tools, a skill that teaches Claude the loop, and
three slash commands.

```bash
claude plugin marketplace add earlzdev/android-driver
claude plugin install android-driver@android-driver
```

There is no venv to manage — the plugin builds the Python server from source on demand, and passes
your project directory to it so your config is found wherever Claude was launched from.

**Requirements:** `adb` and the Android SDK's `emulator` on `PATH`, Python ≥ 3.10. For the faster
uiautomator2 backend run `python -m uiautomator2 init` once per device; without it the server falls
back to a pure-adb backend that needs nothing installed on the device.

Not using Claude Code, or want it as a plain MCP server? It is on PyPI, so there is nothing to clone:

```bash
claude mcp add android-driver -e ANDROID_DRIVER_PROJECT="$PWD" -- uvx android-driver
```

That gets you the tools but not the skill or the slash commands, which are plugin components. See
[docs/installation.md](docs/installation.md) for the config any other MCP client wants.

## Quickstart

```
/android-driver:setup
```

It checks your toolchain, finds your `applicationId` and build command, detects whether you are on
Compose or Views, writes a starter `.android-driver.yaml`, boots an emulator and proves the loop
works. Then:

```
/android-driver:smoke                    # build, install, walk the main flows, assert nothing broke
/android-driver:repro <what is broken>   # reproduce it from a snapshot and leave evidence
```

Or just talk to it — the `android-testing` skill loads automatically when a task involves driving the
app, so "check that login still works on a fresh install" does the right thing without ceremony.

## Why it works this way

Four decisions do most of the work.

**Snapshots, so a repro is actually reproducible.** `snapshot_save` freezes the emulator's exact
state; `snapshot_load` restores it and waits until the device is genuinely drivable again — 1.8–2.2s
measured on a Pixel 7 AVD. Reinstalling and re-navigating costs 30–90s *and drifts a little each
time*. An agent testing thirty variations of a hypothesis needs the cheap, identical option: the
difference between two attempts only means something if everything else was the same.

**A screen index instead of a wall of XML.** A raw `uiautomator dump` is 50–200 KB per screen — tens
of thousands of tokens for a model that just wants to know what it can tap. `screen` returns this:

```
device=emulator-5554 app=com.example.app/.MainActivity screen=1080x2400 driver=uiautomator2
#5  [Scroll]   id=settings_container (scrollable)     @(540,1236)
#7  [Text]     "Settings"  id=homepage_title          @(235,472)
#18 [EditText] "" id=text_field_Bio                   @(540,1018)
```

Then `tap(ref="#7")`. Two orders of magnitude smaller, and it reads like a menu. The raw tree is
still there behind `dump_ui_xml` for when you genuinely need it.

**Assertions that collect their own evidence.** `expect_visible` polls, so it is safe immediately
after a tap and will not flake on an animation; when it fails it hands back the screen index that
*was* there, plus a screenshot and hierarchy dump on disk. `expect_no_crash` reads the `crash` buffer
as well as `main`, because a native abort never reaches `main` at all. Wrap a sequence in
`run_start` / `run_end` and you get `runs/<id>/` holding a timeline, a report, the logcat slice for
exactly that window, and every failure artifact — so an agent cites a directory instead of describing
what it saw.

**Your flows as first-class tools.** The six steps every test starts with — sign in, create an order,
join a call — go into `.android-driver.yaml` once and become real MCP tools with typed parameters. An
agent sees `login(email, password)` in its tool list rather than rediscovering the flow from a screen
dump every session. Recipes run the same code path as the hand-driven tools, so the two cannot drift.

<details>
<summary>Plus the device knowledge that costs an afternoon each to learn</summary>

- **Uninstall-then-install**, not `pm install -r` — debug APKs from different branches carry
  different signing keys and otherwise fail with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`.
- **Check `mInputShown` before pressing Back**, so dismissing the keyboard never dismisses the
  dialog behind it.
- **Write to Compose `TextField`s through the accessibility node**, not tap-then-type, which lands
  text in the wrong field.
- **Settle after a click** before the next query, or you read pre-animation state.
- **An `appops` pass** for OEM permission overlays that keep blocking after `pm grant` reports
  success.

</details>

## Configure

`.android-driver.yaml` at your project root is what makes a generic tool specific to your app.
`/android-driver:setup` writes a starter for you.

```yaml
app:
  package: com.example.myapp
  activity: .MainActivity          # optional; the launcher intent is resolved otherwise

build:
  command: ./gradlew :app:assembleDebug
  apk_glob: app/build/outputs/apk/debug/*.apk

driver:
  backend: auto                    # auto | uiautomator2 | adb

selectors:                         # scanned, so a typo is a warning rather than a mystery
  sources: ["app/src/main/**/*.kt"]

recipes:                           # each becomes an MCP tool with typed parameters
  login:
    params: {email: {required: true}, password: {required: true, secret: true}}
    steps:
      - launch:
      - type: {desc: text_field_Email, text: "{{email}}"}
      - tap: {desc: login_button}
      - expect_visible: {desc: home_greeting, timeout_s: 20}
```

The file is optional: with no config every generic tool still works — you pass `pkg=` explicitly and
lose `build_app` and recipes. It is found by walking up from your project and then, failing that, up
to three levels *down*, so an app in `app/` or `android/` is discovered without configuration.

Full reference: **[docs/configuration.md](docs/configuration.md)** · recipe and step syntax:
**[docs/recipes.md](docs/recipes.md)** · worked examples for Compose and View projects:
[`examples/`](examples/).

## Tools

45, plus one per configured recipe.

| Group | Tools |
|---|---|
| Emulator | `list_avds` `start_emulator` `stop_emulator` `wait_for_boot` `snapshot_save` `snapshot_load` `snapshot_list` `snapshot_delete` |
| Device | `list_devices` `select_device` `device_info` |
| App | `build_app` `install_app` `uninstall_app` `app_info` `launch_app` `force_stop` `clear_app_data` |
| UI | `screen` `tap` `tap_xy` `long_press` `type_text` `swipe` `scroll_to` `press_key` `screenshot` `dump_ui_xml` |
| Assertions | `expect_visible` `expect_gone` `expect_log` `expect_no_crash` |
| Runs | `run_start` `run_end` `run_list` `record_start` `record_stop` |
| Recipes | `list_recipes` `run_recipe` `check_recipes` `list_selectors` `reload_config` |
| Logs | `logcat_clear` `logcat_read` |
| Shell | `shell` |

> [!WARNING]
> `shell` is unrestricted on purpose — this is a development tool, not a sandbox. It can wipe device
> data, kill processes and read files. Point it at emulators and test devices, not at anything you
> care about.

### The loop, in tool calls

```python
start_emulator(avd="Pixel_7")   # reuses one that is already running
install_app(build_first=True)
launch_app()
snapshot_save("clean")          # ← the state every attempt returns to

run_start("issue 412: crash on empty search")
  … login() / tap / type_text / expect_visible …
  expect_no_crash()
run_end()                       # → runs/<id>/report.md

snapshot_load("clean")          # next variation, from identical state
```

[`docs/agent-guide.md`](docs/agent-guide.md) is a `CLAUDE.md` fragment you can drop into a project so
an agent picks this up without being told.

## Try it without your own app

The repo ships **[FlakyDemo](test_app/)** — a Compose app with five screens and **27 deliberately
planted bugs**, each documented in [`test_app/BUGS.md`](test_app/BUGS.md) with what was actually
observed rather than what was intended. Crashes, races, state lost on rotation, a Save button that
reports success and silently does nothing, and several bugs that only show up one run in three.

Its flake generator is seeded, so `--el flake_seed 42` replays the same failures every time and
`--ez flake_enabled false` turns them all off for a clean baseline. It ships with 11 recipes.

It is the fastest way to see what the tool is for — and a fair test of whether it earns its keep,
since a good number of the planted bugs are the kind a tap-and-screenshot agent cannot catch at all.
The Settings screen alone reports "Saved" in the UI while the log says
`outcome=noop reason=terms_not_accepted` and nothing was written.

## Development

```bash
uv sync --extra dev
uv run pytest              # 129 unit tests against a fake driver, no device needed
uv run ruff check src tests
```

Setup, the live suite, and the packaging pitfalls worth knowing about are in
**[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Status

Early, but working end to end. Emulator lifecycle, snapshots, both driver backends, the screen index,
assertions, run bundles, screen recording, recipes and selector scanning are implemented and covered
by tests; the live suite passes against a Pixel 7 AVD. Packaged as a Claude Code plugin with a skill
and three commands.

Not on PyPI — the plugin builds from source, so it does not need to be. Roadmap:
[docs/roadmap.md](docs/roadmap.md). Issues and pull requests welcome.

## License

MIT
