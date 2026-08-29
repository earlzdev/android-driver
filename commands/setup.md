---
description: Bootstrap android-driver for this project — check the toolchain, detect the app, write a starter config, and boot an emulator
argument-hint: "[avd name]"
---

Set this project up for android-driver testing. Work through these in order and report what you found
at each step; stop and explain if something cannot be fixed automatically.

1. **Toolchain.** Confirm `adb` is on PATH and the Android SDK's `emulator` binary exists. Call
   `list_avds` — if it errors, say exactly what the user needs to install.

2. **Detect the app.** Look for `applicationId` in `**/build.gradle` or `**/build.gradle.kts` (fall
   back to the `package` attribute in `AndroidManifest.xml`). Work out the build command and the APK
   glob from the module layout — for a standard Gradle project that is
   `./gradlew :app:assembleDebug` and `app/build/outputs/apk/debug/*.apk`.

3. **Detect the UI toolkit.** Grep for `androidx.compose` in the Gradle files. Compose means the
   `uiautomator2` backend (a tap does not reliably move focus on a Compose `TextField`); a pure View
   project can use `adb`, which needs nothing installed on the device.

4. **Write `.android-driver.yaml`** at the project root with what you found — `app.package`, `build`,
   `driver.backend`, and a `selectors.sources` list pointing at the project's real source directories.
   Show the user the file and explain each choice in one line. If the file already exists, show a diff
   rather than overwriting it.

5. **Boot an emulator.** Use $1 if given, otherwise pick from `list_avds` and say which you chose.
   `start_emulator` reuses one that is already running.

6. **Prove it works.** `install_app(build_first=True)`, `launch_app()`, then `screen`. Show the screen
   index. If the app needs a login to get past the first screen, say so and suggest a `login` recipe
   as the natural next step.

7. **Save a baseline.** `snapshot_save("clean")` once the app is installed and sitting on its starting
   screen, and tell the user that `snapshot_load("clean")` is now their two-second reset.

Finish with a short summary: package, backend, AVD, and what to run next.
