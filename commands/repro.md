---
description: Reproduce a bug on the emulator, varying the approach until it triggers, and produce a run report as evidence
argument-hint: "<what the bug is>"
---

Reproduce this bug on the emulator: **$ARGUMENTS**

The point is a *reliable* repro with evidence, not a lucky one. Work like this:

1. **Get to a known state.** If a `clean` snapshot exists, `snapshot_load("clean")`. If not, install
   and launch the app, navigate to where the bug story starts, and `snapshot_save("clean")` — you will
   want it, because you are about to do this many times.

2. **Read the report before you touch anything.** Use `list_recipes` and `list_selectors` to find the
   flow and the element names this project already has. Do not guess selector names.

3. **Try the obvious path first.** `run_start` with a name that describes the attempt, walk the steps
   the bug report implies, assert what *should* happen with `expect_visible` / `expect_log`, finish
   with `expect_no_crash`, and `run_end`.

4. **If it does not reproduce, vary deliberately.** `snapshot_load("clean")` between every attempt so
   each one starts identical — that is what makes the difference between attempts meaningful. Vary one
   thing at a time: timing, input values, orientation, backgrounding the app, a slower or faster tap
   sequence, an empty or oversized input. Say what hypothesis each attempt is testing.

5. **When it reproduces, prove it.** Do it twice from the same snapshot to show it is deterministic.
   If it only reproduces sometimes, say so and report the rate you observed — an intermittent bug
   reported as intermittent is far more useful than one reported as solid.

6. **Report.** Give the minimal step sequence, the run directory holding the evidence, the specific
   log lines or crash excerpt, and your reading of the likely cause. If you could not reproduce it,
   say what you ruled out and what you would need — a build, an account, a device state — to go
   further. Do not pad a failed repro into a story.
