# Examples

Two configurations covering the ends of the range:

| File | Shape |
|---|---|
| [`compose-app/.android-driver.yaml`](compose-app/.android-driver.yaml) | Jetpack Compose, built from source with Gradle, `uiautomator2` backend, `testTag` selectors |
| [`view-app/.android-driver.yaml`](view-app/.android-driver.yaml) | Classic View system, prebuilt APK, zero-setup `adb` backend, `android:id` selectors |

Copy one to your project root as `.android-driver.yaml` and edit the package name. Or run
`/android-driver:setup`, which detects all of this and writes the file for you.

Nothing in it is required: with no config file at all every generic tool still works — you just pass
`pkg=` explicitly and cannot use `build_app` or recipes.

For a complete, working config on a real app, see
[`test_app/.android-driver.yaml`](../test_app/.android-driver.yaml) — the FlakyDemo app that ships
with this repo, with 11 recipes covering five screens.

## Which driver backend

`uiautomator2` is faster and is the only reliable way to fill a Compose `TextField` — it writes
through the accessibility node instead of tapping and typing, which on Compose can land text in the
wrong field. It needs `python -m uiautomator2 init` once per device.

`adb` needs nothing on the device, so it works in CI containers and on hardware you cannot install a
helper on. Use it for View-system apps, or when setup cost matters more than speed.

`auto` (the default) prefers `uiautomator2` and falls back silently. The startup line on stderr says
which one won.

## Reference

- **[docs/configuration.md](../docs/configuration.md)** — every config key
- **[docs/recipes.md](../docs/recipes.md)** — recipe and step syntax
- **[docs/installation.md](../docs/installation.md)** — install, config discovery, troubleshooting
