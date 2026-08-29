# Roadmap

## M1 — foundation ✅

Packaging, config loader, adb layer, emulator lifecycle + snapshots, both driver backends,
compact screen index, core tool surface.

## M2 — test verbs ✅

- `expect_visible` / `expect_gone` — poll a selector to a deadline, return pass/fail with the screen
  index that was actually there on failure
- `expect_log` — poll logcat for a regex
- `expect_no_crash` — fatal exceptions, ANRs, native aborts and tombstones, read from the `crash`
  buffer as well as `main`, attributed to the app under test
- `run_start` / `run_end` — an artifact bundle per run: screenshots, hierarchy dumps, a logcat slice,
  `timeline.json` and a readable `report.md` under `runs/<id>/`
- `record_start` / `record_stop` — `screenrecord` video, stopped with SIGINT so the MP4 is playable
- Automatic failure artifacts on every action-tool error path, including into a fallback directory
  when no run is open
- `scroll_to` and `long_press`, which the flows kept needing

## M3 — recipes ✅

- YAML flow interpreter; each recipe registered as a real MCP tool with typed parameters, plus a
  generic `run_recipe` escape hatch
- `{{param}}` interpolation that preserves types, `expect_*` steps, per-step `retry` / `optional` /
  `settle_s` / `label`, per-recipe `on_failure`, nested `run`, redaction of `secret` parameters
- Selector scanning: `testTag` / `testSemanticsTag` / `contentDescription` / `android:id` / `R.id` /
  string resources, with runtime-templated literals reported separately; `check_recipes` cross-checks
  every recipe against them and suggests the closest real name

## M4 — release

- ✅ Example configs for a Compose app and a View-system app
- ✅ An agent-facing `CLAUDE.md` fragment consumers can drop in (`docs/agent-guide.md`)
- ✅ Test suite: 104 unit tests against recorded hierarchy fixtures and a fake driver, plus a live
  suite gated on `ANDROID_DRIVER_LIVE=1`
- ✅ GitHub Actions running the unit suite plus a headless-emulator smoke test
- ⬜ PyPI publish
- ⬜ `CONTRIBUTING.md`, issue templates

## Resolved along the way

- **Recipes as a dynamic tool per flow, or one `run_recipe`?** Both. Per-flow tools are what an agent
  discovers; `run_recipe` stays for building a call programmatically. A recipe whose name collides
  with a built-in is registered as `recipe_<name>`.
- **Should the screen index include a stable per-element fingerprint so `#N` survives a redraw?** Not
  needed in practice: the session invalidates the index after anything that can redraw, and `resolve`
  transparently re-reads, so a stale `#N` fails loudly rather than tapping the wrong thing. Prefer
  `desc` / `id` selectors in recipes; `#N` is for interactive use.

## Open questions

- iOS via `idb`, one day, behind the same interface?
- Should `install_app` detect an unchanged APK and skip the reinstall?
- A `dismiss_overlays` hook for OEM permission dialogs — device-specific, and this is an emulator
  tool, so it has been left out so far.
