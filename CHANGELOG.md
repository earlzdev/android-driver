# Changelog

Notable changes per release. Versions follow [semantic versioning](https://semver.org/); until 1.0.0,
minor bumps may break configs and tool signatures.

## 0.1.0 — 2026-09-06

First real release.

### The tool

- **45 built-in tools** over MCP: device and emulator control, UI interaction, a compact screen index
  in place of raw accessibility XML, assertions that save their own evidence, logcat, snapshots, and
  run bundles.
- **Recipes as typed tools.** A named flow in `.android-driver.yaml` is registered as its own MCP
  tool with typed parameters, so an agent sees `login(email, password)` rather than rediscovering six
  steps from a screen dump every session. Recipes and hand-driven tools share one code path, so they
  cannot drift apart.
- **Snapshots for repeatable repros.** `snapshot_save` / `snapshot_load` put the device back in the
  same state, so attempt three starts where attempt one did rather than somewhere downstream of it.
- **`check_recipes`** cross-checks every recipe selector against the `testTag` / `contentDescription`
  / `android:id` literals your sources declare, and reports a rename at startup with a suggestion —
  instead of as "element not found" three steps into a flow.
- Two driver backends: `uiautomator2` (faster, and the only reliable way to fill a Compose
  `TextField`) and pure `adb` (needs nothing on the device). `auto` prefers the first and falls back.

### Distribution

- Published on [PyPI](https://pypi.org/project/android-driver/): `uvx android-driver` for any MCP
  client, no checkout required.
- Installable as a Claude Code plugin, bringing the `android-testing` skill and the
  `/android-driver:setup`, `/android-driver:smoke` and `/android-driver:repro` commands.
- Releases run from a tag over PyPI Trusted Publishing, so no API token exists to leak.

### Fixed since the placeholder

- **The shipped launcher served stale code.** Both configs used `uvx --from <path>`, which keys its
  build cache on `pyproject.toml`'s mtime — so editing anything under `src/` left the cached wheel in
  place and the server kept serving old code, silently, with a normal-looking startup. Both now use
  `uv run --project`, and `tests/test_packaging.py` fails if anyone reintroduces it.
- **`snapshot_load` returned before the device was drivable**, so the next call failed with
  `RemoteDisconnected` or `device offline` — which reads as a broken app rather than a stale session.
  It now waits for boot, and the session drops its connection so the next call rebuilds it.
- **The sdist carried local machine data.** Hatchling reads only the root `.gitignore`, so
  `test_app/.gitignore` and the user's global ignore file were both invisible to it, and the tarball
  shipped `local.properties` with an absolute SDK path. `pyproject.toml` now names what ships, and
  `scripts/check_sdist.py` gates every release on it.
- `markers` was accepted as a config key, parsed, and read by nothing — so setting it produced
  neither an effect nor an error. Removed; it is now rejected like any other unknown key.

## 0.0.1 — 2026-09-03

Placeholder to reserve the name on PyPI. Working code, but not the version to install.
