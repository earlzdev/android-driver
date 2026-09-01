# Recipes

A recipe is a named flow in `.android-driver.yaml`. Each one is registered as **its own MCP tool with
typed parameters**, so an agent sees `login(email, password)` in its tool list rather than
rediscovering six steps from a screen dump every session. They are also reachable through the generic
`run_recipe(name, params)`.

Recipes call the same code path as the hand-driven tools, so the two cannot drift apart.

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
      - type: {desc: text_field_Password, text: "{{password}}"}
      - tap: {desc: login_button}
      - expect_visible: {desc: home_greeting, timeout_s: 20}
```

`description` becomes the tool's description, so write it for the agent that will read it.

## Steps

| | |
|---|---|
| **UI** | `tap` `tap_xy` `long_press` `type` `swipe` `scroll_to` `press` `screenshot` |
| **App** | `build` `install` `uninstall` `launch` `force_stop` `clear_data` |
| **State** | `snapshot_save` `snapshot_load` |
| **Assertions** | `expect_visible` `expect_gone` `expect_log` `expect_no_crash` |
| **Other** | `sleep` `shell` `logcat_clear` `run` |

## Selectors

| | |
|---|---|
| `text` | Matches the element's text exactly. |
| `desc` | Matches `contentDescription` exactly. |
| `contains` | Matches a substring of either, case-insensitively. |
| `id` | Matches a resource id, with or without its package prefix. |
| `ref` | A `#N` from the last `screen` call. |
| `index` | Picks among several matches. Defaults to `0`. |

## Parameters

```yaml
params:
  email:    {required: true}
  wait_s:   {type: int, default: 15}
  password: {required: true, secret: true}
  seed:     {type: int, required: true, description: The same seed replays the same failures}
```

| Key | |
|---|---|
| `type` | `str` (default), `int`, `float`, `bool`. Shows up in the generated tool's schema. |
| `required` | Without a default, the agent must supply it. |
| `default` | Makes the parameter optional. |
| `secret` | Redacted from logs, reports and timelines. Use it for anything you would not paste in a bug report. |
| `description` | Shown to the agent in the tool schema. Worth writing. |

`{{param}}` interpolates anywhere in a step's arguments **and keeps its type** — `timeout_s:
"{{wait_s}}"` arrives as an `int`, not a string.

## Shorthand

A verb with one obvious argument takes a bare scalar:

```yaml
- sleep: 2
- press: back
- tap: "Sign in"          # means text: "Sign in"
- snapshot_load: clean
```

## Per-step options

Write them beside the verb or inside its argument mapping — both work, so use whichever reads better:

```yaml
- expect_visible: {desc: home_greeting, timeout_s: 20, retry: 2}   # inside
- expect_visible: {desc: home_greeting, timeout_s: 20}             # or beside
  retry: 2
```

| Option | |
|---|---|
| `retry: 2` | Re-attempts the step against a **freshly read screen**. This is the right tool for a flow whose first screen is occasionally slow, or an app with a genuinely flaky step. |
| `optional: true` | Lets the step fail without failing the flow. |
| `settle_s: 0.5` | Waits after the step. |
| `label: "confirm the dialog"` | Renames the step in the run report. |

## Failure policy

```yaml
recipes:
  teardown:
    on_failure: continue
    steps: [...]
```

`on_failure: continue` runs the remaining steps after a failure instead of stopping — useful for a
teardown flow where each step is independent. The run still reports the failures.

## Composition

```yaml
- run: {recipe: login, email: "{{email}}"}
```

Calls another recipe, up to five levels deep. Nested steps appear in the report under their recipe's
name (`login.tap`, `login.expect_visible`), so a failure three levels down is still legible.

## Keeping recipes honest

`list_selectors` shows the `testTag` / `contentDescription` / `android:id` / string-resource literals
your project's own sources declare. `check_recipes` cross-checks every recipe against that set and
reports drift at startup, with a suggestion:

```
[recipes] WARNING: login step 4 (`tap`) uses desc='login_buton', which is not among the
                   project's testTag/contentDescription literals. Did you mean 'login_button'?
```

Only `desc` and `id` are checked. A `text` selector matches visible copy that may come from a
translation, a server response or a formatted string, so its absence from the scanned set means
nothing — flagging it would produce noise you learn to ignore, which is worse than not checking.

A rename becomes a warning you see immediately rather than an "element not found" three steps into a
flow. It needs `selectors.sources` to be set — see
[configuration.md](configuration.md#selectors).

## When a step fails

Every step failure saves a screenshot and a hierarchy dump into the run directory, and the failed
step comes back carrying the screen index that *was* there. You can usually see what went wrong
without reproducing it:

```json
{
  "ok": false,
  "error": "step 4 (`expect_visible`) failed: nothing matching {'desc': 'home_greeting'}",
  "failed_step": {
    "index": 4,
    "screenshot": "runs/20260901-074518-smoke/login-4-expect_visible-77432.png",
    "hierarchy":  "runs/20260901-074518-smoke/login-4-expect_visible-77432.xml"
  }
}
```
