---
description: Build, install and walk the app's main flows, asserting nothing crashed — a fast check that a change did not break anything
argument-hint: "[area to focus on]"
---

Run a smoke test of the app. Focus area, if given: **$ARGUMENTS**

1. Open a run: `run_start("smoke")`, which also clears logcat so the log slice covers just this pass.
2. `install_app(build_first=True)`, then `launch_app()`. If the build fails, stop and show the build
   output — that is the answer, not something to work around.
3. If the project has recipes, run them. They encode the flows that matter here, and they are cheaper
   and more reliable than rediscovering the same steps from screen dumps.
4. Otherwise walk the app yourself: from the start screen, visit each primary navigation destination,
   assert something specific is visible on each with `expect_visible`, and take a `screenshot` of each.
   Use `scroll_to` for anything below the fold.
5. Exercise at least one text input and one list, since those break most often.
6. `expect_no_crash()` at the end.
7. `run_end()`, then report: pass or fail, the run directory, and for any failure the step, the
   screenshot path, and the relevant log lines.

Keep it under a few minutes. This is a smoke test — depth belongs in `/android-driver:repro`.
