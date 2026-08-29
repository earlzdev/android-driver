# Agent guide

Drop this into your project's `CLAUDE.md` / `AGENTS.md` (or point at it) so an
agent picks up the loop instead of rediscovering it.

---

## Driving the Android app under test

An `emulator` MCP server is attached. It drives an Android emulator: build,
install, tap, assert, snapshot, reset.

**Read the screen with `screen`, not `dump_ui_xml`.** `screen` returns one line
per actionable element with a `#N` you can tap. The raw XML is 50–200 KB and
will eat the context you need for the actual work. Reach for `dump_ui_xml` only
when you need an attribute `screen` does not surface.

**Prefer a stable selector over coordinates.** `tap(desc="login_button")` keeps
working after a layout change; `tap_xy(540, 1320)` does not. `list_selectors`
shows the names the app's own sources declare.

**Snapshot before you explore.** Get the app into the state a bug starts from,
then `snapshot_save("clean")`. Every later attempt is `snapshot_load("clean")` —
two seconds and byte-identical, against 30–90 seconds of reinstalling and
re-navigating that drifts a little each time. This is what makes it practical to
test thirty variations of a hypothesis instead of three.

**Assert, don't eyeball.** `expect_visible` polls, so it is safe to call right
after a tap and it will not flake on an animation. `expect_no_crash` reads the
crash buffer as well as `main`, so it catches native aborts a screenshot cannot
show. A failing assertion is a normal result with `passed: false`, not an error.

**Open a run for anything you will report on.** `run_start("what you are
testing")` clears logcat and starts recording every action with its timing;
`run_end` writes `runs/<id>/report.md` plus the log slice and any failure
screenshots. Cite the run directory rather than describing what you saw.

**Check for a recipe first.** `list_recipes` shows the flows this project has
already encoded. Each is also a tool of its own with typed parameters — use
`login(email=..., password=...)` rather than reconstructing it step by step. If
you work out a flow that will be needed again, propose adding it to
`.android-driver.yaml`.

### The usual loop

```
start_emulator(avd="Pixel_7")   # reuses it if already running
install_app(build_first=True)
launch_app()
snapshot_save("clean")          # ← the state every attempt returns to
run_start("issue 412: crash on empty search")
  … tap / type / expect_visible …
  expect_no_crash()
run_end()
snapshot_load("clean")          # next variation, from identical state
```

### Failure handling

Every failed action already saved a screenshot and a hierarchy dump — the paths
come back in the result. A failed `expect_visible` also returns the screen index
that *was* there. Read those before retrying: a second identical attempt is
rarely the answer, and the evidence usually names the problem.

If a tap reports "no element matches", the screen most likely changed under you.
Call `screen` again rather than guessing coordinates.
