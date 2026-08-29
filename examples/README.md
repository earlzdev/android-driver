# Examples

Two configurations covering the ends of the range:

| File | Shape |
|---|---|
| [`compose-app/.android-driver.yaml`](compose-app/.android-driver.yaml) | Jetpack Compose, built from source with Gradle, `uiautomator2` backend, `testTag` selectors |
| [`view-app/.android-driver.yaml`](view-app/.android-driver.yaml) | Classic View system, prebuilt APK, zero-setup `adb` backend, `android:id` selectors |

Copy one to your project root as `.android-driver.yaml` and edit the package name.
Nothing in it is required: with no config file at all every generic tool still
works — you just pass `pkg=` explicitly and cannot use `build_app` or recipes.

## Which driver backend

`uiautomator2` is faster and is the only reliable way to fill a Compose
`TextField` — it writes through the accessibility node instead of tapping and
typing, which on Compose can land text in the wrong field. It needs
`python -m uiautomator2 init` once per device.

`adb` needs nothing on the device, so it works in CI containers and on hardware
you cannot install a helper on. Use it for View-system apps, or when setup cost
matters more than speed.

`auto` (the default) prefers `uiautomator2` and falls back silently.

## Writing a recipe

A recipe is a named flow that becomes its own MCP tool with typed parameters, so
an agent sees `login(email, password)` rather than rediscovering six steps from a
screen dump every session.

```yaml
recipes:
  login:
    description: Sign in and land on the home screen
    params:
      email: {required: true}
      password: {required: true, secret: true}   # redacted from logs and reports
    steps:
      - launch:                                   # a step with no arguments
      - type: {desc: text_field_Email, text: "{{email}}"}
      - tap: {desc: login_button}
      - expect_visible: {desc: home_greeting, timeout_s: 20}
```

**Steps.** `tap` `tap_xy` `long_press` `type` `swipe` `scroll_to` `press`
`screenshot` · `build` `install` `uninstall` `launch` `force_stop` `clear_data` ·
`snapshot_save` `snapshot_load` · `expect_visible` `expect_gone` `expect_log`
`expect_no_crash` · `sleep` `shell` `logcat_clear` `run`.

**Selectors.** `text` and `desc` match exactly, `contains` matches a substring of
either, `id` matches a resource id with or without its package prefix, `ref` is a
`#N` from `screen`. Use `index` to pick among several matches.

**Shorthand.** A verb with one obvious argument takes a bare scalar: `sleep: 2`,
`press: back`, `tap: "Sign in"` (which means `text`), `snapshot_load: clean`.

**Per-step options.** `retry: 2` re-attempts against a freshly read screen.
`optional: true` lets a step fail without failing the flow. `settle_s: 0.5` waits
after the step. `label: "confirm the dialog"` renames it in the report.

**Failure policy.** `on_failure: continue` at the recipe level runs the remaining
steps after a failure instead of stopping — useful for a teardown flow where each
step is independent.

**Composition.** `- run: {recipe: login, email: "{{email}}"}` calls another
recipe, up to five levels deep.

Every step failure saves a screenshot and a hierarchy dump, and the failed step
comes back with the screen index that *was* there — so you can usually see what
went wrong without reproducing it.
