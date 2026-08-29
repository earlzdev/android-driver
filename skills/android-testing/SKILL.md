---
name: android-testing
description: Drive an Android app on an emulator to test it, reproduce a bug, or verify a change — read screens, tap, type, assert, snapshot for identical repro attempts, and collect run evidence. Use whenever the task involves exercising an Android app through the android-driver tools, or when the user asks to test, reproduce, or check something on an emulator or device.
---

# Testing an Android app with android-driver

The `android-driver` MCP tools drive an emulator: build, install, tap, assert, snapshot, reset.

## Read the screen with `screen`, not `dump_ui_xml`

`screen` returns one line per actionable element with a `#N` you can tap:

```
#1 [Button] "Sign in" desc=login_button @(540,1320)
#2 [EditText] "" hint="Email" @(540,980)
```

The raw XML behind `dump_ui_xml` is 50–200 KB per screen and will eat the context you need for
the actual work. Reach for it only when you need an attribute `screen` does not surface.

## Prefer a stable selector over coordinates

`tap(desc="login_button")` survives a layout change; `tap_xy(540, 1320)` does not. `list_selectors`
shows the `testTag` / `contentDescription` / `android:id` / string-resource literals the project's own
sources declare — use it instead of guessing a name.

## Snapshot before you explore

Get the app to the state the bug starts from, then `snapshot_save("clean")`. Every later attempt is
`snapshot_load("clean")` — about two seconds, and byte-identical. Reinstalling and re-navigating costs
30–90 seconds and drifts a little each time. This is what makes it practical to test thirty variations
of a hypothesis instead of three, so reach for it early rather than after the third slow reset.

## Assert, don't eyeball

- `expect_visible` / `expect_gone` poll to a deadline, so they are safe right after a tap and will not
  flake on an animation.
- `expect_log` polls logcat for a regex. Clear the buffer first, or open a run, or a match left over
  from a previous attempt will pass it trivially.
- `expect_no_crash` reads the `crash` buffer as well as `main`, so it catches native aborts and ANRs
  that a screenshot cannot show.

A failed assertion is a normal result with `passed: false`, not an error. It comes back with the
screen index that *was* there, plus a screenshot and hierarchy dump on disk.

## Open a run for anything you will report on

`run_start("what you are testing")` clears logcat and starts timing and recording every action.
`run_end` writes `runs/<id>/report.md`, `timeline.json`, the logcat slice for exactly that window, and
every failure artifact. Cite the run directory rather than narrating what you saw.

## Check for a recipe first

`list_recipes` shows the flows this project has already encoded. Each is also a tool of its own with
typed parameters — call `login(email=..., password=...)` rather than rebuilding it step by step. If you
work out a flow that will be needed again, propose adding it to `.android-driver.yaml`.

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

## When something fails

Every failed action already saved a screenshot and a hierarchy dump; the paths come back in the
result. Read those before retrying — a second identical attempt is rarely the answer, and the evidence
usually names the problem.

"No element matches" almost always means the screen changed under you. Call `screen` again rather than
guessing coordinates. If the element is below the fold, `scroll_to` swipes until it appears.

## Setup problems

- No device: `list_devices` is empty → `start_emulator(avd=...)`, and `list_avds` shows what exists.
- `build_app` unavailable → the project has no `build.command` in `.android-driver.yaml`; install a
  prebuilt APK with `install_app(apk_path=...)` instead.
- Text landing in the wrong field on Compose → the uiautomator2 backend handles this correctly; check
  `device_info` and the server's startup log to see which backend is active.
