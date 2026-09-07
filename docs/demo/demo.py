#!/usr/bin/env python3
"""The demo behind the README's recording: a flake, pinned.

Runs against the FlakyDemo app in `test_app/`, and shows the one thing the tool
exists for — BUG-LOG-01 fails about one login in three at random, which is
undebuggable, and a snapshot plus a seed turns it into a case that replays
exactly.

Nothing here is staged. It speaks to a real `android-driver` server over stdio
and prints what the tools actually return, so you can run it yourself:

    python docs/demo/demo.py

Needs a booted emulator with FlakyDemo installed and a snapshot named `clean`
saved on the login screen. `--setup` does all of that from a cold start.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
TEST_APP = REPO / "test_app"

# The seeds BUGS.md documents for BUG-LOG-01. The whole demo rests on these two
# behaving differently every single time, which is the claim being made.
SEED_FAILS = 24
SEED_PASSES = 20

BOLD, DIM, RED, GREEN, YELLOW, RESET = (
    "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[0m",
)


class Server:
    """An MCP server running as a subprocess, spoken to over stdio."""

    def __init__(self, project: Path) -> None:
        env = {**os.environ, "ANDROID_DRIVER_PROJECT": str(project)}
        self.proc = subprocess.Popen(
            ["uv", "run", "--project", str(REPO), "android-driver"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # the startup banner would clutter the recording
            env=env,
            text=True,
            bufsize=1,
        )
        self._id = 0
        self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "android-driver-demo", "version": "1"},
        })
        self._notify("notifications/initialized")

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._id += 1
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}) + "\n"
        )
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("the server exited")
            msg = json.loads(line)
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg["result"]

    def _notify(self, method: str) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    # `name` is positional-only so a tool argument called `name` — `run_recipe`
    # has one — does not collide with this parameter.
    def call(self, name: str, /, **args: Any) -> dict[str, Any]:
        result = self._rpc("tools/call", {"name": name, "arguments": args})
        return json.loads(result["content"][0]["text"])

    def close(self) -> None:
        self.proc.terminate()


def say(text: str = "") -> None:
    print(text, flush=True)


def beat(seconds: float) -> None:
    """A pause, so the recording is readable at 1x."""
    time.sleep(seconds)


LAUNCH_FLAKY = "am start -n com.earldev.flakydemo/.MainActivity --ez reset_store true"
EMAIL, PASSWORD = "demo@test.dev", "hunter2"


def outcome(result: dict[str, Any], brief: bool = False) -> str:
    """The verdict for one attempt.

    `brief` keeps act 2 on one line: by then the reader has already seen the
    full error once, and three wrapped lines would bury the thing worth seeing,
    which is that the two seed-24 runs agree.
    """
    if result.get("ok"):
        return f"{GREEN}\u2713{RESET}  dashboard_greeting"
    if brief:
        return f"{RED}\u2717{RESET}  dashboard_greeting not found"
    return f"{RED}\u2717{RESET}  {result.get('error', 'failed')[:72]}"


def sign_in(s: Server) -> dict[str, Any]:
    """One login attempt, driven tool by tool the way you would do it by hand.

    Deliberately *not* the `login` recipe. That one carries `retry: 2` precisely
    so BUG-LOG-01 does not fail a flow — which would hide the thing act 1 is
    about. Three consecutive flakes are rare, so the recipe almost always passes.
    """
    s.call("force_stop")
    s.call("shell", cmd=LAUNCH_FLAKY)
    time.sleep(2.5)
    s.call("type_text", desc="text_field_Email", text=EMAIL)
    s.call("type_text", desc="text_field_Password", text=PASSWORD)
    s.call("tap", desc="login_button")
    return s.call("expect_visible", desc="dashboard_greeting", timeout_s=6)


def act1(s: Server, cap: int) -> None:
    say(f"{BOLD}1. The bug{RESET}   {DIM}BUG-LOG-01 \u2014 login fails about one attempt in three{RESET}")
    say()
    say(f"   {DIM}force_stop \u2192 launch \u2192 type email \u2192 type password \u2192 tap login_button"
        f" \u2192 expect_visible{RESET}")
    say()
    for attempt in range(1, cap + 1):
        result = sign_in(s)
        say(f"   attempt {attempt}   {outcome(result)}")
        if not result.get("ok"):
            banner = s.call("expect_visible", desc="login_error_banner", timeout_s=2)
            if banner.get("ok"):
                say(f'               {DIM}login_error_banner: "Network unavailable."{RESET}')
            say()
            say(f"   {DIM}Reproduced on attempt {attempt}. Run it again and it may well pass.{RESET}")
            break
        beat(0.3)
    else:
        say()
        say(f"   {YELLOW}No failure in {cap} attempts. It is random \u2014 that is the problem.{RESET}")
    say()
    beat(1.2)


def act2(s: Server) -> None:
    say(f"{BOLD}2. Pinned{RESET}   {DIM}the device back to a known state, the flake generator seeded{RESET}")
    say()
    plan = [(SEED_FAILS, "same seed"), (SEED_FAILS, "same seed"), (SEED_PASSES, "different seed")]
    for seed, label in plan:
        snap = s.call("snapshot_load", name="clean")
        say(f"   snapshot_load clean            {DIM}{snap.get('seconds')}s{RESET}")
        s.call("run_recipe", name="login_seeded", params={"seed": seed})
        result = s.call("expect_visible", desc="dashboard_greeting", timeout_s=6)
        say(f"   login_seeded seed={seed}         {outcome(result, brief=True)}   {DIM}{label}{RESET}")
        if not result.get("ok"):
            # Name the branch the app actually took, rather than inferring it
            # from the absence of a dashboard.
            confirmed = s.call("expect_log", pattern="login_result outcome=network_error", timeout_s=5)
            if confirmed.get("ok"):
                say(f"   {DIM}expect_log login_result outcome=network_error   {GREEN}\u2713{RESET}")
        say()
        beat(0.6)
    say(f"   {DIM}Seed 24 fails every time, seed 20 passes every time, and the phone's{RESET}")
    say(f"   {DIM}login footer shows which seed is live. Visible, not asserted.{RESET}")
    say()
    beat(1.2)


def act3(s: Server, run_dir: str) -> None:
    say(f"{BOLD}3. The evidence{RESET}   {DIM}saved without being asked{RESET}")
    say()
    path = Path(run_dir)
    if not path.exists():
        return
    say(f"   {path.relative_to(TEST_APP)}/")
    # Alphabetical would open on screenshot filenames. The written artefacts are
    # what a person reads first, so lead with those and let the evidence follow.
    lead = ["report.md", "timeline.json", "logcat.txt", "logcat-app.txt"]
    def order(f: Path) -> tuple[int, str]:
        return (lead.index(f.name) if f.name in lead else len(lead), f.name)

    files = sorted(path.iterdir(), key=order)
    annotated = False
    for f in files:
        note = ""
        if f.name == "logcat.txt":
            note = f"   {DIM}\u2190 sliced to this run's window{RESET}"
        elif f.suffix == ".png" and not annotated:
            # Once. The same arrow on every screenshot is noise, and the reader
            # can see for themselves that there are three of them.
            note = f"   {DIM}\u2190 the screen at each failure{RESET}"
            annotated = True
        say(f"      {f.name}{note}")
    say()
    say(f"   {DIM}In Claude Code this is one prompt:{RESET}  /android-driver:repro BUG-LOG-01")
    say()


def setup(s: Server, avd: str) -> None:
    # Reuse a device that is already up. Booting one this script did not start
    # would also mean choosing GPU flags for it, and the person running the demo
    # has usually already made that choice.
    devices = s.call("list_devices").get("devices", [])
    if devices:
        say(f"{DIM}using the attached device {devices[0]['serial']}{RESET}")
    else:
        say(f"{DIM}booting {avd}...{RESET}")
        s.call("start_emulator", avd=avd)
    say(f"{DIM}installing FlakyDemo...{RESET}")
    s.call("install_app", build_first=False)
    # The snapshot has to be taken on the login screen: that is where every
    # seeded attempt begins, and restoring anywhere else would need extra steps
    # the demo would have to show and explain.
    s.call("run_recipe", name="login_deterministic", params={})
    s.call("snapshot_save", name="clean")
    say(f"{GREEN}ready{RESET} — snapshot 'clean' saved on the login screen")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--setup", action="store_true", help="boot, install and save the 'clean' snapshot")
    ap.add_argument("--avd", default="Pixel_7")
    ap.add_argument("--attempts", type=int, default=5, help="how long act 1 waits for the flake")
    args = ap.parse_args()

    s = Server(TEST_APP)
    try:
        if args.setup:
            setup(s, args.avd)
            return 0

        say()
        run = s.call("run_start", name="demo", note="a flake, pinned")
        act1(s, args.attempts)
        act2(s)
        s.call("run_end")
        act3(s, run["dir"])
        return 0
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())
