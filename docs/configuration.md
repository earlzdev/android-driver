# Configuration reference

`.android-driver.yaml` at your project root. Every section is optional; so is the file itself.
`/android-driver:setup` writes a starter for you, and
[`examples/`](../examples/) has complete configs for a Compose project and a View-system project.

Where the file is looked for, and how to point at a specific one, is covered in
[installation.md](installation.md#how-the-config-is-found).

## `app`

```yaml
app:
  package: com.example.myapp
  activity: .MainActivity
```

| Key | Default | |
|---|---|---|
| `package` | — | The `applicationId`. Without it, every tool that touches the app needs an explicit `pkg=`. |
| `activity` | resolved | The activity to launch. Omit it and the launcher intent is resolved from the manifest, which is usually what you want. |

## `build`

```yaml
build:
  command: ./gradlew :app:assembleDebug
  apk_glob: app/build/outputs/apk/debug/*.apk
  timeout_s: 900
```

| Key | Default | |
|---|---|---|
| `command` | — | Run by `build_app`, from the project root. Without it `build_app` and `install_app(build_first=True)` are unavailable. |
| `apk_glob` | — | Where to find the APK the build produced. If several match, the newest wins. |
| `apk` | — | A fixed APK path, for projects that do not build from source. Use instead of `command` + `apk_glob`. |
| `timeout_s` | `900` | Gradle cold builds are slow; this is deliberately generous. |

## `install`

```yaml
install:
  strategy: uninstall-then-install
  grant_runtime_perms: true
  appops: [CAMERA, RECORD_AUDIO]
```

| Key | Default | |
|---|---|---|
| `strategy` | `uninstall-then-install` | Or `reinstall`. The default is not arbitrary: debug APKs built from different branches carry different signing keys, and `pm install -r` then fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. Choose `reinstall` when you deliberately want app data preserved across installs. |
| `grant_runtime_perms` | `true` | Grants every runtime permission the manifest declares, so a permission dialog never blocks a flow. |
| `appops` | `[]` | An `appops set` pass for the named permissions. Some OEM images keep blocking after `pm grant` reports success; this is the workaround. |

## `timing`

```yaml
timing:
  cold_start_settle_s: 2.0
  click_settle_s: 0.25
  boot_timeout_s: 300
  default_find_timeout_s: 10
```

| Key | Default | |
|---|---|---|
| `cold_start_settle_s` | `2.0` | Waited after a cold launch before the first UI query. Compose recomposition after a long idle regularly takes seconds on slow hardware; undersleeping races the first tap and produces "element not found" on a screen that is perfectly fine. Raise it if you see that. |
| `click_settle_s` | `0.25` | Waited after each click. Many Compose buttons render as `android.view.View` with `clickable=false` in the accessibility tree, so a fast follow-up query catches pre-animation state and misses the screen currently transitioning in. |
| `boot_timeout_s` | `300` | How long `start_emulator` and `wait_for_boot` wait for a device to come up. |
| `default_find_timeout_s` | `10` | Default `timeout_s` for `expect_visible` and friends. |

## `driver`

```yaml
driver:
  backend: auto
```

| Value | |
|---|---|
| `auto` (default) | Prefers `uiautomator2`, falls back to `adb` when it is unavailable. The startup line on stderr says which one won. |
| `uiautomator2` | Faster, and the only reliable way to fill a Compose `TextField` — it writes through the accessibility node instead of tapping and typing, which on Compose can land text in the wrong field. Needs `python -m uiautomator2 init` once per device. Erroring rather than falling back is the point of naming it explicitly. |
| `adb` | Needs nothing on the device, so it works in CI containers and on hardware you cannot install a helper on. Good for View-system apps, or when setup cost matters more than speed. |

## `selectors`

```yaml
selectors:
  sources:
    - "app/src/main/**/*.kt"
    - "app/src/main/res/values/strings.xml"
```

Globs, relative to the project root, that `list_selectors` scans for the selector literals your app
actually declares: Compose `testTag` and `testSemanticsTag`, `contentDescription`, `android:id`,
`R.id.*`, and string resources.

This is what makes `check_recipes` useful: it cross-checks every selector in every recipe against
this set and reports a rename as a warning at startup, with a `difflib` suggestion, rather than as
"element not found" three steps into a flow.

## `recipes`

Named flows that become MCP tools with typed parameters. Full syntax in
**[recipes.md](recipes.md)**.

```yaml
recipes:
  login:
    description: Sign in and land on the home screen
    params:
      email: {required: true}
      password: {required: true, secret: true}
    steps:
      - launch:
      - type: {desc: text_field_Email, text: "{{email}}"}
      - tap: {desc: login_button}
      - expect_visible: {desc: home_greeting, timeout_s: 20}
```

## Where output goes

`runs/` under the project root, one directory per `run_start`, holding `report.md`, `timeline.json`,
the logcat slice for exactly that window, and any screenshots and hierarchy dumps saved by failing
steps. Add it to `.gitignore`.

## Typos fail loudly

An unknown top-level key is a hard error, not a silently ignored line:

```
ConfigError: /path/.android-driver.yaml: unknown top-level key(s): ['apps']
```

That is deliberate. A config that half-loads is worse than one that refuses to, because the symptom
shows up much later as a missing tool or a mysterious "element not found".
