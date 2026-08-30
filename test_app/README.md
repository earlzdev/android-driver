# FlakyDemo

A Jetpack Compose app built to be *tested*, not used — a fixture for exercising
[android-driver](https://github.com/earlzdev/android-driver). Five screens, every kind of Material
control, a real landscape layout on each one, and **27 planted bugs**: some deterministic, some
intermittent, three of them crashes.

**[BUGS.md](BUGS.md) is the catalogue** — all 27 defects with repro steps, expected/actual, and how
to detect each one, plus the element inventory for every screen. Each entry was reproduced on a
Pixel 7 AVD and records what was actually observed.

## The screens

| # | Route | Source | Bugs |
|---|---|---|---|
| 1 | `login` | `screens/LoginScreen.kt` | [5](BUGS.md#1--login) |
| 2 | `dashboard` | `screens/DashboardScreen.kt` | [5](BUGS.md#2--dashboard) |
| 3 | `catalog` | `screens/CatalogScreen.kt` | [5](BUGS.md#3--catalog) |
| 4 | `settings` | `screens/SettingsScreen.kt` | [6](BUGS.md#4--settings) |
| 5 | `detail/<id>` | `screens/DetailScreen.kt` | [6](BUGS.md#5--item-detail) |

Navigation is a single saveable back-stack string (`login|dashboard|catalog|detail/13`), logged on
every transition, so `expect_log(pattern="stack=")` tells you exactly where the app thinks it is.

## Run it

```bash
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.earldev.flakydemo/.MainActivity
```

Credentials: `demo@test.dev` / `hunter2` (anything with an `@` and six or more password characters).

## Controlling the flakiness

Every intermittent bug draws from one seeded generator, so a "random" failure is replayable:

```bash
# Replay an exact session. The same seed always produces the same failures.
adb shell am start -n com.earldev.flakydemo/.MainActivity --el flake_seed 24

# Turn every flaky bug off, leaving only the deterministic ones.
adb shell am start -n com.earldev.flakydemo/.MainActivity --ez flake_enabled false

# Reset the in-memory store (catalog, settings, session) without reinstalling.
adb shell am start -n com.earldev.flakydemo/.MainActivity --ez reset_store true
```

The seed in use is printed at startup (`FlakyDemo: flake init seed=24 enabled=true`) and shown in
`login_footer` on screen. Every coin flip is logged:

```
D FlakyDemo: flake name=login_network_error n=1 rate=0.3 roll=0.11 hit=true
W FlakyDemo: flake FIRED name=login_network_error
```

That gives three levels of control: **off** for a baseline, **seeded** for a deterministic repro,
and **free-running** for the flake hunt itself.

## Selectors

Every interactive element carries the same string twice — as a Compose `testTag` and as a
`contentDescription` (`Modifier.driverTestTag`, `ui/Common.kt`). The root opts into
`testTagsAsResourceId`, so a tag shows up as `resource-id` in the hierarchy:

```
<node resource-id="login_button" content-desc="login_button" class="android.view.View" clickable="true" .../>
```

Either `id=login_button` or `desc=login_button` resolves it. The recipes in `.android-driver.yaml`
use `desc:` because that is the pool `list_selectors` scans and `check_recipes` validates against.

The helper and its callers are named so the scanner can find them — `driverTestTag("…")` and
`testTag = "…"` both match its built-in patterns, which is why `list_selectors` reports **132 tags**
here and `check_recipes` comes back clean:

```
$ list_selectors
  tag        132
  text        16
  templates   20   # computed names: catalog_item_${item.id}, tab_$name, ${testTag}_value …
```

Names built at runtime — `catalog_item_13`, `tab_Reviews`, `stat_orders_value`,
`settings_banner_text` — are real at runtime but are reported as templates, not literals, so recipes
that need them should assert on the stable parent instead.

## Things worth knowing before you drive it

- **The IME does not close on ESC.** Compose text fields need `press(back)` — check `mInputShown`
  first so you dismiss the keyboard and not the screen behind it.
- **Swiping from the left edge is a back gesture,** not a scroll. Scroll from the middle.
- **Banners live for 2.5 seconds.** A `uiautomator dump` can take longer than that; use
  `expect_visible`, which polls, rather than dumping and reading.
- **Sliders need a `swipe` along the track.** Tapping a Compose `Slider` does not move it.
- **Truncated text is invisible to the hierarchy.** Compose reports the full string in semantics
  even when the pixels are ellipsised, so no bug here relies on visual truncation — the landscape
  bugs are missing elements and wrong values instead.
- **The delete dialog is its own window** with its own composition root. It opts into
  `testTagsAsResourceId` separately; a dialog that forgets to do that exposes no tags at all.

## Suggested exercises

1. **A flake, pinned.** Run `login` ten times and watch it fail intermittently (BUG-LOG-01). Then
   find a failing seed, and turn the flake into a case that fails every single time.
2. **One variable at a time.** BUG-DET-04 crashes on item 13 and not on item 12. Snapshot the
   catalog, then vary only the item id.
3. **Orientation as the variable.** BUG-SET-05 and BUG-DSH-04 are invisible in portrait. Run the
   same recipe in both orientations and diff the result.
4. **Trust the store, not the toast.** BUG-SET-01 and BUG-SET-03 both show "Saved". Only
   `stored_summary` knows the truth.
5. **Crash hunting.** Three crashes with three different causes. BUG-DET-04 is dead reliable (3/3),
   BUG-DSH-05 needs a precise input burst, and BUG-SET-06 throws every time but only kills the
   process about two runs in three — so `expect_no_crash` alone under-reports it and `expect_log`
   does not. A fourth defect (BUG-CAT-02) logs an exception without dying at all, which is the case
   for reading logcat rather than trusting a liveness check.

## Project layout

```
app/src/main/java/com/earldev/flakydemo/
  MainActivity.kt          nav stack, flake knobs, testTagsAsResourceId opt-in
  core/Flake.kt            the single source of non-determinism, seeded and logged
  core/Data.kt             the deterministic 60-item catalog
  core/AppStore.kt         process-level state; the dropped-write path
  ui/Common.kt             driverTestTag, PillButton, StatCard, Banner, AppTopBar
  screens/                 one file per screen
```
