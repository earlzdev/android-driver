# FlakyDemo — the planted bugs

All 27 defects in the app, grouped by screen. Every one has been reproduced on a Pixel 7 AVD; each
entry records what was actually observed, not what was intended.

Setup, selector conventions and the flake-seed knobs are in [README.md](README.md).

| ID | Screen | Kind | Frequency |
|---|---|---|---|
| BUG-LOG-01 | [Login](#1--login) | Random network failure | ~1 in 3 |
| BUG-LOG-02 | [Login](#1--login) | Email lost on rotation | Always |
| BUG-LOG-03 | [Login](#1--login) | Double tap signs in twice | Always, on a double tap |
| BUG-LOG-04 | [Login](#1--login) | Untrimmed email blamed on the password | Always |
| BUG-LOG-05 | [Login](#1--login) | Guest button missing in landscape | Always |
| BUG-DSH-01 | [Dashboard](#2--dashboard) | Refresh serves the previous period | ~1 in 4 |
| BUG-DSH-02 | [Dashboard](#2--dashboard) | Period and counter reset on rotation | Always |
| BUG-DSH-03 | [Dashboard](#2--dashboard) | Sync bar stalls at 90% | ~1 in 5 |
| BUG-DSH-04 | [Dashboard](#2--dashboard) | Errors/Uptime transposed in landscape | Always |
| BUG-DSH-05 | [Dashboard](#2--dashboard) | **Crash** — `ArithmeticException` | 3+ refreshes inside 2 s |
| BUG-CAT-01 | [Catalog](#3--catalog) | Search settles on a stale query | Timing-dependent |
| BUG-CAT-02 | [Catalog](#3--catalog) | Wrong item, or a tap that does nothing | Tap within 400 ms of a filter change |
| BUG-CAT-03 | [Catalog](#3--catalog) | Query and scroll lost on rotation | Always |
| BUG-CAT-04 | [Catalog](#3--catalog) | Load more advances two pages | ~1 in 3 |
| BUG-CAT-05 | [Catalog](#3--catalog) | Odd result set loses a row in landscape | Always |
| BUG-SET-01 | [Settings](#4--settings) | Save no-ops but reports success | While terms unaccepted |
| BUG-SET-02 | [Settings](#4--settings) | Unsaved draft discarded on rotation | Always |
| BUG-SET-03 | [Settings](#4--settings) | Acknowledged write dropped | ~1 in 5 |
| BUG-SET-04 | [Settings](#4--settings) | Cache size silently rounded to 64s | Always |
| BUG-SET-05 | [Settings](#4--settings) | Landscape save discards text fields | Always |
| BUG-SET-06 | [Settings](#4--settings) | **Crash** — `StringIndexOutOfBoundsException` | Bio over 100 chars; fatal ~2 runs in 3 |
| BUG-DET-01 | [Detail](#5--item-detail) | Cancelled delete stays armed | Always |
| BUG-DET-02 | [Detail](#5--item-detail) | Deletes the neighbouring item | ~1 in 4 |
| BUG-DET-03 | [Detail](#5--item-detail) | Tab resets on rotation | Always |
| BUG-DET-04 | [Detail](#5--item-detail) | **Crash** — `NoSuchElementException` | Items 13 and 42 |
| BUG-DET-05 | [Detail](#5--item-detail) | Total lags the quantity by one unit | ~1 in 3 |
| BUG-DET-06 | [Detail](#5--item-detail) | Landscape tabs off by one | Always |

---

# 1 — Login

Route `login` · `LoginScreen.kt` · entry point of the app.

The sign-in form. Every other screen is reachable only through it, so its flaky failures are the
ones most likely to break an unrelated test three screens later.

**Portrait** — one scrolling column: the wordmark, then the form.
**Landscape** — a two-pane `Row`: a fixed branding pane on the left (40%) and the scrolling form on
the right (60%). The panes are separate code paths, which is where BUG-LOG-05 lives.

**Credentials.** Anything with an `@` and a password of six characters or more is accepted.
`demo@test.dev` / `hunter2` is the pair the recipes use. `guest_button` signs in as `guest@local`.

| Selector | Kind | Notes |
|---|---|---|
| `brand_title`, `brand_subtitle` | Text | Subtitle only exists in landscape |
| `login_root_portrait` / `login_root_landscape` | Container | Tells you which branch rendered |
| `login_heading` | Text | "Sign in" |
| `login_error_banner`, `login_error_banner_text` | Banner | Present only after a failed attempt |
| `text_field_Email` | EditText | Validated **untrimmed** — see BUG-LOG-04 |
| `text_field_Password` | EditText | Masked unless the switch is on; `password="true"` in the dump |
| `remember_me_checkbox`, `remember_me_label` | Checkbox | Purely decorative; nothing reads it |
| `show_password_switch`, `show_password_label` | Switch | Toggles the visual transformation |
| `login_button` | Button | **Never disabled**, even mid-request — see BUG-LOG-03 |
| `login_progress` | Spinner | Sits *beside* the button while a request is in flight |
| `login_attempt_counter` | Text | "Attempts this session: N", survives rotation |
| `guest_button` | Button | Portrait only — see BUG-LOG-05 |
| `login_footer` | Text | Shows the active flake seed, e.g. `FlakyDemo build 1.0 · seed 24` |

### BUG-LOG-01 — sign-in fails at random with "Network unavailable"

**Repro.** Enter valid credentials and tap `login_button`.

**Expected.** The dashboard.

**Actual.** Roughly one attempt in three shows `login_error_banner` reading *"Network unavailable.
Check your connection."* and stays on the login screen. Tapping again usually works.

**Detecting it.** `expect_visible(desc="dashboard_greeting")` right after the tap flakes. The
`login` recipe carries `retry: 2` for exactly this reason.

**Pinning it down.** The failure is drawn from one seeded generator, so it replays exactly:

```
run_recipe("login_seeded", {"seed": 24})   # always fails
run_recipe("login_seeded", {"seed": 20})   # always succeeds
```

`expect_log(pattern="login_result outcome=network_error")` confirms which path ran, and
`--ez flake_enabled false` removes the failure entirely. This is the bug to reach for when
demonstrating that a snapshot plus a seed turns a flake into a deterministic case.

### BUG-LOG-02 — the email field is emptied by a rotation, the password field is not

**Repro.** Type into both fields, rotate to landscape and back.

**Expected.** Both fields keep their contents.

**Actual.** `text_field_Email` is empty; `text_field_Password` still holds its value. The email is
held in a plain `remember`, the password in a `rememberSaveable`, so a configuration change drops
exactly one of the two.

**Detecting it.** Read both fields' `text` before and after `rotate_landscape` / `rotate_portrait`.
Verified: `before email='demo@test.dev'` → `after email=''`, password unchanged.

### BUG-LOG-03 — a double tap signs in twice and pushes the dashboard onto the stack twice

**Repro.** Fill the form, then tap `login_button` twice about 100 ms apart.

**Expected.** One sign-in; Back from the dashboard returns to login.

**Actual.** Two requests run; both succeed; the back stack becomes `login|dashboard|dashboard`.
Pressing Back from the dashboard lands on the dashboard again.

**Why it survives.** The request is launched on a process-level scope (`AppStore.appScope`), the way
a ViewModel or repository would own one, so the second job is not cancelled when the screen leaves
composition. The button is never disabled and the spinner appears next to it rather than replacing
it, so there is nothing to stop the second tap.

**Detecting it.** `expect_log(pattern="login_submit")` fires twice, and the `screen=` log line shows
`stack=login|dashboard|dashboard`. Then `press(back)` and assert you are on login — you will not be.

### BUG-LOG-04 — a leading space in the email is reported as a wrong password

**Repro.** Enter `" demo@test.dev"` (leading space) with a valid password.

**Expected.** Either the address is trimmed and accepted, or the error names the email.

**Actual.** `login_error_banner` reads *"Password is incorrect."* The validator compares
`email != email.trim()` and reports the failure through the password branch's message, so the error
points at the wrong field.

**Detecting it.** The distinguishing signal is in logcat, not on screen:
`login_result outcome=rejected reason=email_shape` versus `reason=password_length`. A test that only
reads the banner cannot tell the two apart — which is the point.

### BUG-LOG-05 — "Continue as guest" does not exist in landscape

**Repro.** Rotate to landscape on the login screen.

**Expected.** The same controls as portrait.

**Actual.** `guest_button` is absent from the hierarchy entirely — not merely off-screen. The
landscape branch was written separately and the control was left behind in the portrait one, so the
whole guest flow is unreachable until the device is rotated back.

**Detecting it.** `expect_gone(desc="guest_button")` passes in landscape and
`expect_visible(desc="guest_button")` passes in portrait. Verified against both orientations.

---

# 2 — Dashboard

Route `dashboard` · `DashboardScreen.kt` · reached by signing in.

The hub: period-scoped statistics, a sync job, a counter, and the navigation into the other three
screens. Its bugs are the ones that make an assertion on a *value* worth writing, because every one
of them leaves the screen looking perfectly healthy.

**Portrait** — a scrolling column; the four stat cards sit in a 2×2 grid.
**Landscape** — a `Row`: the scrolling body on the left, a fixed 420dp "Recent activity" panel on
the right. The stat cards become a single four-across row, a separate code path — see BUG-DSH-04.

| Selector | Kind | Notes |
|---|---|---|
| `dashboard_top_bar`, `screen_title` | Top bar | Title is "Dashboard" |
| `orientation_readout` | Text | Literally `portrait` / `landscape`; handy as a rotation barrier |
| `dashboard_greeting` | Text | "Signed in as demo@test.dev" — the marker that login succeeded |
| `period_chip_row` | LazyRow | Horizontal, scrollable |
| `period_chip_Today` / `_Week` / `_Month` / `_Year` | Button | Selecting one triggers a refresh |
| `period_readout` | Text | "Showing: Week" — the *requested* period |
| `stat_orders`, `stat_revenue`, `stat_errors`, `stat_uptime` | Card | Each with `_label` and `_value` children |
| `avg_per_day` | Text | Computed on refresh; the divisor is BUG-DSH-05 |
| `refresh_button`, `refresh_progress` | Button / Text | Progress text only while in flight |
| `sync_button`, `sync_block`, `sync_percent`, `sync_progress_bar` | Button / bar | See BUG-DSH-03 |
| `counter_minus`, `counter_value`, `counter_plus`, `lifetime_taps` | Stepper | `counter_value` is screen-local, `lifetime_taps` is process-level |
| `nav_catalog_button`, `nav_settings_button`, `featured_item_button` | Button | Featured opens item **13**, which has no reviews (see BUG-DET-04) |
| `dropped_writes` | Text | Counts settings saves silently discarded by BUG-SET-03 |
| `logout_button` | Button | Returns to login and clears the stack |
| `activity_panel`, `activity_panel_title`, `activity_row_1..6` | Panel | Landscape only |

**Reference values.** Assertions can be exact — the numbers per period are fixed:

| Period | `stat_orders_value` | `stat_revenue_value` | `stat_errors_value` | `stat_uptime_value` |
|---|---|---|---|---|
| Today | `42` | `$1,284.00` | `3` | `99.1%` |
| Week | `310` | `$9,640.00` | `11` | `98.7%` |
| Month | `1288` | `$41,250.00` | `47` | `99.4%` |
| Year | `15402` | `$502,180.00` | `512` | `99.9%` |

### BUG-DSH-01 — a refresh serves the previous period's numbers under the new period's heading

**Repro.** Tap through several period chips, each of which refreshes.

**Expected.** `period_readout` and the four card values always describe the same period.

**Actual.** About one refresh in four re-serves the period that was rendered last. The header still
says "Showing: Week" while the cards hold Today's numbers.

**Detecting it.** Assert on values, not on presence: select `Week`, then
`expect_visible(text="310")` for `stat_orders_value`. Verified — the log records the mismatch
directly: `dashboard_refresh_done requested=Week served=Today`.

### BUG-DSH-02 — the period selection and the counter reset on rotation

**Repro.** Select `Week`, tap `counter_plus` twice, rotate.

**Expected.** Still Week, counter still 2.

**Actual.** `period_readout` is back to "Showing: Today" and `counter_value` is `0`. Both are held
in a plain `remember`. `lifetime_taps`, which lives in the process-level store, keeps its value —
so the same screen shows one counter that survived and one that did not.

**Detecting it.** Verified: `before=('Showing: Week', '2')` → `after=('Showing: Today', '0')`.
Read `counter_value` in portrait; in landscape it sits below the fold.

### BUG-DSH-03 — the sync bar stops at 90% and never finishes

**Repro.** Tap `sync_button` a few times.

**Expected.** The bar fills and `sync_block` disappears.

**Actual.** About one sync in five stops updating at 90%. `sync_percent` reads "Sync 90%" and
`sync_progress_bar` stays on screen indefinitely.

**Detecting it.** `expect_gone(desc="sync_block", timeout_s=10)` hangs to its deadline and fails.
`expect_log(pattern="dashboard_sync outcome=stalled")` names it outright; the healthy path logs
`outcome=complete`.

### BUG-DSH-04 — Errors and Uptime swap values in landscape

**Repro.** Rotate the dashboard to landscape and read the last two cards.

**Expected.** With Today selected: `stat_errors_value` = `3`, `stat_uptime_value` = `99.1%`.

**Actual.** `stat_errors_value` = `99.1%` and `stat_uptime_value` = `3`. The landscape row is a copy
of the portrait one with the last two values transposed. Both cards are present and both *labels*
are correct, so a presence assertion passes and only a value assertion catches it.

**Detecting it.** Verified in landscape: `errors='99.1%' uptime='3'`. Note that a screenshot alone
is unconvincing here — the values are plausible-looking either way.

### BUG-DSH-05 — three refreshes inside two seconds crash the app

**Repro.** Tap `refresh_button` three times with ~150 ms between taps.

**Expected.** Three refreshes.

**Actual.** `java.lang.ArithmeticException: divide by zero`, and the process dies. The
average-per-day calculation divides by `refreshTimes.size - 3`, and the third tap inside the
two-second window leaves that at zero.

Verified boundary, by PID before and after:

| Input | Outcome |
|---|---|
| 2 taps, 150 ms apart | survives |
| 3 taps, 150 ms apart | **dead** — `ArithmeticException: divide by zero` |
| 4 taps, 150 ms apart | **dead** — the third tap already armed it |
| 3 taps, 1.2 s apart | survives — the window pruned the first |

**Detecting it.** `expect_no_crash()` after the burst; the exception reaches the `crash` buffer.
Note the button must not move between taps — an earlier build put the "Refreshing…" readout *above*
the button row, which shifted it out from under the next tap and made the bug impossible to trigger
by coordinates. It now sits below the buttons.

---

# 3 — Catalog

Route `catalog` · `CatalogScreen.kt` · reached from the dashboard's "Open catalog".

A searchable, filterable, sortable list of 60 items over a `LazyColumn`, with paging. This is the
screen for exercising scrolling, debounced input, and the difference between "the element is not
there" and "the element is not there *yet*".

**Portrait** — one row per item.
**Landscape** — two items per row, built by chunking the list into pairs. The chunking is where
BUG-CAT-05 lives.

**The data.** 60 items, generated deterministically, so a repro can name a row by id and get the
same row every time. Item `n` is named `"<Adjective> <Noun> <100+n>"`, priced `400 + (n*137) % 9600`
cents, and carries `(n % 4) + 1` reviews — **except items 13 and 42, which have none** (that is the
fuel for BUG-DET-04 on the detail screen).

| Query | Matches | Why it is useful |
|---|---|---|
| `113` | exactly 1 (item 13) | Smallest odd result set — the cleanest BUG-CAT-05 repro |
| `Storage` | 15 (a category) | Odd result set large enough to need scrolling |
| `Cedar` | 6 (an adjective) | Even result set — the control case |
| `zzz` | 0 | Empty state |

| Selector | Kind | Notes |
|---|---|---|
| `catalog_top_bar`, `back_button`, `screen_title` | Top bar | |
| `result_count` | Text | "60 found" — counts the **filtered** set, not the rendered rows |
| `search_field` | EditText | Debounced with a variable delay; see BUG-CAT-01 |
| `filter_chip_All`, `filter_chip_In_stock`, `filter_chip_On_sale` | Button | Spaces become underscores in the tag |
| `sort_toggle` | Button | Cycles "Sort: Name" ⇄ "Sort: Price" |
| `search_progress` | Text | "Searching…" while a query is in flight |
| `catalog_summary` | Text | `Showing 20 of 60 · query "Cedar"` — the *applied* query, which may lag what is typed |
| `catalog_list` | LazyColumn | `scrollable="true"` |
| `catalog_item_<id>` | Row | Clickable; with `item_name_<id>`, `item_category_<id>`, `item_price_<id>`, `item_stock_<id>` |
| `load_more_button` | Button | At the end of the list |
| `catalog_empty_state`, `empty_message` | Text | Only when nothing matches |

### BUG-CAT-01 — the list can settle on the results of a query you have already moved past

**Repro.** Type a query quickly, character by character.

**Expected.** The list ends up matching what is in the box.

**Actual.** Every keystroke launches its own delayed job and nothing cancels the previous one. The
delay is jittered, so a slower earlier job can land last and repaint the list with results for an
earlier prefix. `search_field` and `catalog_summary` then disagree.

**Detecting it.** Compare the query in `search_field` with the one quoted in `catalog_summary`; the
summary reports what was actually applied. Verified with 50 ms between keystrokes: the field read
`Cedar` while the summary read `query "Ceda"`, and the jobs finished in the order

```
catalog_search query=Ced   count=6
catalog_search query=Ce    count=6
catalog_search query=C     count=38   ← the list briefly showed 38 rows for "Cedar"
catalog_search query=Cedar count=6
catalog_search query=Ceda  count=6    ← this one landed last and won
```

Typing through `type_text` in one shot mostly hides this — it needs per-character input to surface,
which makes it a good case for `shell "input text"` versus the driver's own typing.

### BUG-CAT-02 — tapping a row just after changing a filter opens a different item

**Repro.** Tap `filter_chip_On_sale` and, with no pause at all, tap a row.

**Expected.** The row you tapped opens.

**Actual.** The tap resolves the row through its **position** in the list as it was when the row was
composed, so a filter change landing between composition and tap opens something else. Two distinct
symptoms, depending on how far down the row is:

| Row index | Outcome | Evidence |
|---|---|---|
| Within the new list (e.g. 2) | A **different item** opens | `catalog_open index=2 tapped=24 opening=30` — reproduced identically three times in a row, landing on "Copper Lamp 130" |
| Beyond it (e.g. 15, when "On sale" leaves 12) | The tap **does nothing at all** | `ArrayIndexOutOfBoundsException: length=12; index=15` in logcat; the process survives |

**Detecting it.** Not a process crash — `expect_no_crash()` passes. The assertion that catches it is
`expect_visible` on the item you meant to open: `tap(desc="catalog_item_24")` followed by
`expect_visible(text="Amber Lamp 124")` fails, because the screen says "Copper Lamp 130". The
second symptom is worse: the tap reports success and the screen simply never changes, which looks
exactly like a missed tap until you read the log. Waiting for `search_progress` to disappear before
tapping makes the whole sequence harmless.

### BUG-CAT-03 — the search query and the scroll position are lost on rotation

**Repro.** Search for `Cedar`, scroll down, rotate.

**Expected.** The query and roughly the same position.

**Actual.** `search_field` is empty and the list is back at the top showing all 60 items.

**Detecting it.** Verified: `before='Showing 6 of 6 · query "Cedar"'` → `after='Showing 20 of 60 ·
query ""'`. This one interferes with testing the other landscape bugs — rotate *first*, then search.

### BUG-CAT-04 — "Load more" sometimes advances two pages instead of one

**Repro.** Press `load_more_button` repeatedly and watch `catalog_summary`.

**Expected.** "Showing N" grows by 10 each time.

**Actual.** About one press in three grows it by 20.

**Detecting it.** Verified over five presses: steps were `10, 10, 20, 20, 10`. The log line is
`catalog_load_more from=40 step=20 to=60`. Because the underlying list is a fixed 60 items, nothing
is actually lost — the visible symptom is only the jump in the count.

### BUG-CAT-05 — landscape silently drops the last row of an odd-length result set

**Repro.** Rotate to landscape, then search `113`.

**Expected.** One row, matching the "1 found" header.

**Actual.** `result_count` says "1 found", `catalog_summary` says "Showing 1 of 1", and the list
renders **nothing**. The landscape layout chunks the list into pairs and iterates the pairs, so the
unpaired tail is discarded — one row vanishes from every odd-length result set.

**Detecting it.** Verified: portrait renders `catalog_item_13`, landscape renders no rows, with an
identical header in both. `Storage` (15 matches) shows the same thing at scale: 15 counted, 14
rendered. The header/list disagreement is the assertion worth writing.

---

# 4 — Settings

Route `settings` · `SettingsScreen.kt` · reached from the dashboard's "Open settings".

The widest variety of input controls in the app — three text fields, three switches, a radio group,
a continuous slider, a dropdown menu and a checkbox — behind a Save button that lies about what it
did. Four of its six bugs are silent: the UI reports success and the data does not change.

**Portrait** — one scrolling column. `save_button` sits below the fold; a single swipe reaches it.
**Landscape** — two panes: the text fields scroll on the left, the toggles and the action row sit on
the right. The right pane has its own save path, which is BUG-SET-05.

| Selector | Kind | Notes |
|---|---|---|
| `settings_top_bar`, `back_button`, `screen_title` | Top bar | |
| `settings_banner`, `settings_banner_text` | Banner | "Saved" / "Reset to defaults"; **clears itself after 2.5 s** |
| `stored_summary` | Text | `Stored: Demo User · 256 MB · sync Hourly` — reads the store, not the draft. The ground truth for every save assertion |
| `text_field_DisplayName`, `text_field_Email`, `text_field_Bio` | EditText | Bio is multi-line |
| `bio_preview` | Text | Crashes for certain lengths — BUG-SET-06 |
| `switch_notifications`, `switch_dark_mode`, `switch_analytics` | Switch | Each with `_label` and `_row` |
| `radio_sync_Manual` / `_Hourly` / `_Daily` | RadioButton | Plus `radio_sync_label_*` and `sync_option_row_*` |
| `cache_size_value`, `cache_size_slider` | Text / Slider | Continuous 0–1024; drag it, a tap will not move it |
| `region_dropdown_button`, `region_dropdown_menu`, `region_option_Europe` … | Dropdown | Spaces become underscores (`region_option_Asia_Pacific`) |
| `terms_checkbox`, `terms_label` | Checkbox | **Gates whether Save does anything at all** |
| `save_button`, `reset_button` | Button | Save is never disabled |

### BUG-SET-01 — Save reports success and does nothing while the terms box is unchecked

**Repro.** Change the display name, scroll to `save_button`, tap it. Leave `terms_checkbox` alone.

**Expected.** Either the change is saved, or Save is disabled with a visible reason.

**Actual.** `settings_banner_text` reads "Saved" and `stored_summary` is unchanged. The guard that
should have disabled the button lives inside the save handler and returns early — after setting the
success banner.

**Detecting it.** Assert on `stored_summary`, never on the banner. Verified: the banner says "Saved"
while the log says `settings_save outcome=noop reason=terms_not_accepted`. Ticking `terms_checkbox`
first makes the same save persist correctly, which is the control case.

**Timing note.** The banner clears itself after 2.5 s, and a `uiautomator dump` can take longer than
that. Read it promptly or use `expect_visible`, which polls.

### BUG-SET-02 — a rotation throws away every unsaved edit, without warning

**Repro.** Edit the display name, rotate, rotate back.

**Expected.** The edit survives, or the user is warned.

**Actual.** Every field is back to the last saved value. The whole draft is a plain `remember`
seeded from the store.

**Detecting it.** Verified: `before='Demo UserY'` → `after='Demo User'`. Note this also makes
BUG-SET-05 harder to test — retype in landscape after rotating.

### BUG-SET-03 — one save in five is acknowledged and then thrown away

**Repro.** Accept the terms, then press Save repeatedly.

**Expected.** Every save persists.

**Actual.** About one in five is dropped. The banner still says "Saved"; `stored_summary` keeps the
old value; the dashboard's `dropped_writes` counter goes up.

**Detecting it.** Verified over eight saves: `['true','true','false','true','true','true','false','true']`.
The log distinguishes them: `settings_save acknowledged=true persisted=false dropped=2`. This is the
one bug in the app whose evidence is easiest to gather across a *loop* of attempts from a snapshot
rather than in a single pass.

### BUG-SET-04 — the cache size is silently rounded to a multiple of 64

**Repro.** Drag `cache_size_slider` to any value, accept the terms, Save.

**Expected.** `stored_summary` shows what the slider showed.

**Actual.** The store keeps only multiples of 64. Verified: the slider read `413 MB`, the stored
summary read `384 MB`. Reopening the screen shows the rounded number.

**Detecting it.** Read `cache_size_value` before Save and the MB figure in `stored_summary` after.
Note the slider needs a `swipe` along its track — `tap_xy` on a Compose `Slider` does not move it.

### BUG-SET-05 — the landscape Save writes the toggles and discards the text fields

**Repro.** In landscape: edit `text_field_DisplayName`, accept the terms, flip a switch, Save.

**Expected.** Both the name and the switch persist.

**Actual.** The switch, region and cache size are written; the display name, email and bio are not.
The landscape pane got its own save path that rebuilds the payload from the *stored* profile fields
instead of the draft. In portrait the same edits save correctly.

**Detecting it.** Verified: typed `Demo UserZed` in landscape, `stored_summary` still read
`Demo User`. Running the same steps in portrait as a control is what makes this diagnosable — the
orientation is the only variable.

### BUG-SET-06 — a bio longer than 100 characters throws, and usually kills the app

**Repro.** Type 110 characters into `text_field_Bio`.

**Expected.** A truncated preview.

**Actual.** `java.lang.StringIndexOutOfBoundsException: begin 0, end 120, length 101`. The guard
tests for more than 100 characters and the slice asks for 120, so any length from 101 to 119 throws
while the preview recomposes — on the keystroke, not on Save.

**The part that makes it interesting.** The exception is thrown every time; the process death is
not. Across three identical runs at 110 characters:

| Trial | Outcome |
|---|---|
| 1 | exception logged at length 104, **process survived** |
| 2 | exception logged at length 101, **process died** |
| 3 | exception logged at length 101, **process died** |

So `expect_no_crash()` alone is an unreliable detector here — it passes about one run in three. The
robust assertion is `expect_log(pattern="StringIndexOutOfBoundsException")`, which fires every time.
That contrast is the point of keeping this bug in the fixture.

**Note on how the text is entered.** Typing character by character (`adb shell input text`) walks the
string through the fatal 101–119 window, so even a 130-character bio trips it on the way past — the
observed failure at 130 characters threw at length 102. A driver that writes the whole string through
the accessibility node in one step may land outside the window instead; worth checking which
behaviour your backend produces.

**Detecting it.** A boundary worth bisecting: 100 characters is safe, 101 is not.

---

# 5 — Item detail

Route `detail/<id>` · `DetailScreen.kt` · reached from a catalog row, or from the dashboard's
"Open featured item" (which opens item **13**).

Tabs, an expandable section, a rating row, a quantity stepper and a destructive action behind a
confirmation dialog. This is where the two nastiest bugs live: one that deletes something the user
never confirmed, and one that deletes the wrong thing.

**Portrait** — three tabs: Overview, Specs, Reviews.
**Landscape** — a fixed 300dp gallery pane on the left, and **four** tabs: Gallery, Overview, Specs,
Reviews. The extra tab is what makes BUG-DET-06 an off-by-one.

| Selector | Kind | Notes |
|---|---|---|
| `detail_top_bar`, `back_button`, `screen_title`, `detail_id_badge` | Top bar | Badge reads `#13` |
| `detail_progress` | Progress bar | Brief, on entry |
| `detail_banner`, `detail_banner_text` | Banner | "Added 2 × …", "Link copied"; clears after 2.5 s |
| `pending_delete_banner`, `_text` | Banner | "Delete confirmation is still armed." — the tell for BUG-DET-01 |
| `tab_Overview`, `tab_Specs`, `tab_Reviews`, `tab_Gallery` | Button | `tab_Gallery` is landscape only |
| `tab_content_overview` / `_specs` / `_reviews` | Container | Which one is present tells you what actually rendered |
| `detail_name`, `detail_category`, `detail_unit_price`, `detail_stock`, `detail_hero_image` | Overview | |
| `specs_expander`, `specs_expander_label`, `specs_expanded_block` | Expander | Contains `spec_sku`, `spec_weight`, `spec_warranty`, `spec_origin` |
| `rating_star_1..5`, `rating_value` | Rating | Survives rotation (`rememberSaveable`) |
| `top_review_card`, `top_review_title`, `top_review_meta`, `top_review_body`, `review_row_<i>` | Reviews | See BUG-DET-04 |
| `qty_minus`, `qty_value`, `qty_plus`, `total_value` | Stepper | `qty_value` survives rotation; `total_value` does not |
| `add_to_cart_button`, `share_button`, `delete_button` | Button | All three route through one handler — see BUG-DET-01 |
| `delete_dialog`, `delete_dialog_title`, `delete_dialog_body`, `delete_confirm_button`, `delete_cancel_button` | Dialog | A separate window; it opts into `testTagsAsResourceId` on its own |
| `last_deleted_readout` | Text | "Last deleted: …" — process-level, so it survives navigation |
| `detail_gallery_pane`, `gallery_title`, `gallery_thumb_1..3` | Panel | Landscape only |
| `detail_missing_message` | Text | When the id no longer exists in the catalog |

### BUG-DET-01 — cancelling the delete dialog leaves the delete armed for the next tap

**Repro.** Tap `delete_button`, then `delete_cancel_button`. Then tap `add_to_cart_button`.

**Expected.** Cancel means nothing is deleted, and Add to cart adds to the cart.

**Actual.** The item is deleted and you are returned to the catalog. Every primary action funnels
through one handler that consumes a pending confirmation before doing its own work, and Cancel
dismisses the dialog without disarming it. Rotating the dialog away does the same thing — the
dialog's visibility is a plain `remember`, the armed flag is a `rememberSaveable`, so a rotation
hides the dialog and keeps the intent.

**Detecting it.** `pending_delete_banner_text` appears after Cancel and reads "Delete confirmation
is still armed." Verified end to end: Add to cart navigated away, and the log reads
`detail_pending_consumed by=add_to_cart` followed by `detail_delete requested=4 deleted=4`.

### BUG-DET-02 — the delete removes the row after the one you opened

**Repro.** Open an item, delete it, and check `last_deleted_readout` and the catalog.

**Expected.** The item you opened.

**Actual.** About one delete in four resolves the victim by the position the row held before the
catalog was last re-sorted, and removes its neighbour instead.

**Detecting it.** The log gives both sides: `detail_delete requested=4 deleted=5 name=…`. From the
UI, compare `detail_name` before the delete with `last_deleted_readout` after it, or search the
catalog for the item that should be gone. Because the outcome is seeded, `login_seeded` plus a fixed
seed replays the same choice every time — which is the cheapest way to get a deterministic case out
of this one. Verified on item 4 across ten seeds: seeds 12 and 14 deleted item 4 correctly, seeds
16, 18 and 20 deleted item 5 instead.

### BUG-DET-03 — the selected tab resets to Overview on rotation

**Repro.** Select Specs, rotate, rotate back.

**Expected.** Still Specs.

**Actual.** Overview. The tab index is a plain `remember`; the quantity right below it is a
`rememberSaveable` and survives, so the same screen loses one and keeps the other.

**Detecting it.** Verified: after rotation `tab_content_overview` is present and `tab_content_specs`
is gone. Assert on the `tab_content_*` container, not on which chip looks selected.

### BUG-DET-04 — the Reviews tab crashes for an item with no reviews

**Repro.** From the dashboard, tap `featured_item_button` (item 13), then `tab_Reviews`.

**Expected.** An empty-state message.

**Actual.** `java.util.NoSuchElementException: List is empty.` The "top review" card calls `.first()`
with no guard. Items **13** and **42** are the two with no reviews; every other item is fine, which
is what makes this look like a flake until you notice which item it was.

**Detecting it.** `expect_no_crash()` after selecting the tab. Verified dead reliable — three of
three runs killed the process. A good demonstration of varying one thing at a time from a snapshot:
same steps, item 12 → fine, item 13 → dead.

### BUG-DET-05 — the total is one unit behind the quantity

**Repro.** Press `qty_plus` several times and compare `qty_value` with `total_value`.

**Expected.** `total_value` = unit price × `qty_value`.

**Actual.** About a third of the presses price the order from the pre-increment quantity, so the
total sticks at the previous step's value while the quantity moves on.

**Detecting it.** Verified on item 4 (unit price $9.48): quantity/total pairs
`2→1896, 3→1896, 4→3792, 5→4740, 6→5688, 7→5688, 8→7584` — the entries at quantity 3 and 7 are one
step behind. An assertion has to compute the expected total; presence checks see nothing wrong.

### BUG-DET-06 — every landscape tab shows the content of the tab after it

**Repro.** Rotate to landscape, tap `tab_Overview`.

**Expected.** Overview.

**Actual.** Specs. Landscape prepends a Gallery tab to the row but the content dispatch still uses
the portrait indices, so the whole strip is off by one: Gallery → Overview, Overview → Specs,
Specs → Reviews, Reviews → Reviews.

**Detecting it.** Verified: tabs are `[tab_Gallery, tab_Overview, tab_Specs, tab_Reviews]`, and after
tapping `tab_Overview` the visible container is `tab_content_specs`. Note this also puts the crashing
Reviews content one tab earlier than expected, so on item 13 in landscape it is `tab_Specs` that
kills the app.
