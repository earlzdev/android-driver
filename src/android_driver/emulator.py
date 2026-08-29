"""AVD lifecycle and snapshots — the determinism layer.

Snapshots are the reason this package exists. Reinstalling an app and walking it
back to a known screen costs 30-90 seconds; loading a snapshot costs 2-5. For an
agent doing bug-repro-by-variation, that difference is the difference between
exploring three hypotheses and exploring thirty.

The emulator console is reached through `adb emu <cmd>`, which handles the
console auth token for us — no ~/.emulator_console_auth_token juggling.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .adb import AdbError, list_devices, shell
from .adb import _adb as _adb_raw
from .log import log


class EmulatorError(RuntimeError):
    pass


def sdk_root() -> Path:
    """Locate the Android SDK. Honours ANDROID_HOME / ANDROID_SDK_ROOT, then guesses."""
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(var)
        if value and Path(value).is_dir():
            return Path(value)
    for guess in (
        Path.home() / "Library/Android/sdk",  # macOS
        Path.home() / "Android/Sdk",  # Linux
        Path.home() / "AppData/Local/Android/Sdk",  # Windows
    ):
        if guess.is_dir():
            return guess
    raise EmulatorError(
        "Android SDK not found. Set ANDROID_HOME to your SDK directory "
        "(e.g. ~/Library/Android/sdk on macOS)."
    )


def emulator_binary() -> Path:
    path = sdk_root() / "emulator" / "emulator"
    if not path.is_file():
        raise EmulatorError(
            f"emulator binary not found at {path}. Install it via Android Studio's "
            "SDK Manager, or `sdkmanager emulator`."
        )
    return path


def list_avds() -> list[str]:
    result = subprocess.run(
        [str(emulator_binary()), "-list-avds"], text=True, capture_output=True, check=False, timeout=60
    )
    if result.returncode != 0:
        raise EmulatorError(f"emulator -list-avds failed: {result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def avd_name_of(serial: str) -> str | None:
    """Ask a running emulator which AVD it is. Returns None for physical devices."""
    if not serial.startswith("emulator-"):
        return None
    result = _adb_raw(["-s", serial, "emu", "avd", "name"], check=False, timeout=15)
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and line != "OK":
            return line
    return None


def running_emulators() -> dict[str, str | None]:
    """Map serial → AVD name for every attached emulator."""
    return {
        d["serial"]: avd_name_of(d["serial"])
        for d in list_devices()
        if d["serial"].startswith("emulator-")
    }


def is_booted(serial: str) -> bool:
    """True once the framework is up AND the boot animation has finished.

    `sys.boot_completed` alone is not enough: it flips while the boot animation is
    still playing, and UI automation against that window fails in ways that look
    like flaky selectors rather than "the device is not ready yet".
    """
    try:
        completed = shell(serial, "getprop", "sys.boot_completed", check=False, timeout=15).strip()
        bootanim = shell(serial, "getprop", "init.svc.bootanim", check=False, timeout=15).strip()
    except AdbError:
        return False
    return completed == "1" and bootanim == "stopped"


def wait_for_boot(serial: str, timeout_s: int = 300, poll_s: float = 2.0) -> dict:
    """Block until `serial` has fully booted."""
    deadline = time.monotonic() + timeout_s
    started = time.monotonic()
    while time.monotonic() < deadline:
        if is_booted(serial):
            elapsed = round(time.monotonic() - started, 1)
            log("emulator", f"{serial} booted in {elapsed}s")
            return {"ok": True, "serial": serial, "boot_seconds": elapsed}
        time.sleep(poll_s)
    return {"ok": False, "serial": serial, "error": f"boot timeout after {timeout_s}s"}


def start(
    avd: str,
    *,
    headless: bool = False,
    cold_boot: bool = False,
    wipe_data: bool = False,
    snapshot: str | None = None,
    writable_system: bool = False,
    extra_args: list[str] | None = None,
    boot_timeout_s: int = 300,
) -> dict:
    """Boot an AVD and wait for it to be usable. Returns its serial.

    If the AVD is already running, returns the existing serial instead of booting a
    second copy — an agent that calls `start_emulator` defensively at the top of
    every run should not end up with four emulators fighting over the same ports.
    """
    available = list_avds()
    if avd not in available:
        raise EmulatorError(f"unknown AVD {avd!r}. Available: {available}")

    already = {name: serial for serial, name in running_emulators().items() if name}
    if avd in already:
        serial = already[avd]
        log("emulator", f"{avd} already running as {serial}; reusing")
        return {"ok": True, "serial": serial, "avd": avd, "reused": True}

    before = {d["serial"] for d in list_devices()}
    cmd = [str(emulator_binary()), "-avd", avd]
    if headless:
        cmd += ["-no-window", "-no-audio"]
    if cold_boot:
        cmd += ["-no-snapshot-load"]
    if wipe_data:
        cmd += ["-wipe-data"]
    if snapshot:
        cmd += ["-snapshot", snapshot]
    if writable_system:
        cmd += ["-writable-system"]
    cmd += extra_args or []

    log("emulator", f"launching: {' '.join(cmd)}")
    # Detached: the emulator outlives this call and must not die with the MCP
    # server's process group, nor block on a pipe nobody reads.
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.monotonic() + boot_timeout_s
    serial: str | None = None
    while time.monotonic() < deadline and serial is None:
        time.sleep(2.0)
        for candidate in {d["serial"] for d in list_devices()} - before:
            if candidate.startswith("emulator-"):
                serial = candidate
                break
    if serial is None:
        raise EmulatorError(
            f"{avd} did not appear in `adb devices` within {boot_timeout_s}s. "
            f"Try launching it by hand to see the error: {' '.join(cmd)}"
        )

    remaining = max(30, int(deadline - time.monotonic()))
    boot = wait_for_boot(serial, timeout_s=remaining)
    return {**boot, "avd": avd, "serial": serial, "reused": False}


def stop(serial: str) -> dict:
    """Shut down a running emulator via its console."""
    result = _adb_raw(["-s", serial, "emu", "kill"], check=False, timeout=30)
    combined = result.stdout + result.stderr
    if result.returncode != 0 and "OK" not in combined:
        raise EmulatorError(f"could not stop {serial}: {combined.strip()}")
    for _ in range(15):
        if serial not in {d["serial"] for d in list_devices()}:
            return {"ok": True, "serial": serial}
        time.sleep(1.0)
    return {"ok": False, "serial": serial, "error": "still attached 15s after `emu kill`"}


# ── snapshots ─────────────────────────────────────────────────────────────────


def _snapshot_cmd(serial: str, *args: str) -> str:
    if not serial.startswith("emulator-"):
        raise EmulatorError(f"{serial} is not an emulator — snapshots are emulator-only.")
    result = _adb_raw(["-s", serial, "emu", "avd", "snapshot", *args], check=False, timeout=180)
    combined = (result.stdout + result.stderr).strip()
    # The console answers "KO: <reason>" on its own line. Substring-matching "KO"
    # against the whole blob would also fire on a snapshot named e.g. "OKO".
    failed = any(line.strip().startswith("KO") for line in combined.splitlines())
    if result.returncode != 0 or failed:
        raise EmulatorError(f"snapshot {' '.join(args)} on {serial} failed: {combined}")
    return combined


def snapshot_save(serial: str, name: str) -> dict:
    """Freeze the device's exact current state under `name`.

    Save right after your app is installed, permissions granted, and you are on the
    screen a test starts from. Every later `snapshot_load(name)` returns to exactly
    that point, so a repro attempt starts from identical state every time.
    """
    started = time.monotonic()
    _snapshot_cmd(serial, "save", name)
    return {"ok": True, "serial": serial, "snapshot": name, "seconds": round(time.monotonic() - started, 1)}


def snapshot_load(serial: str, name: str) -> dict:
    started = time.monotonic()
    _snapshot_cmd(serial, "load", name)
    return {"ok": True, "serial": serial, "snapshot": name, "seconds": round(time.monotonic() - started, 1)}


def snapshot_delete(serial: str, name: str) -> dict:
    _snapshot_cmd(serial, "delete", name)
    return {"ok": True, "serial": serial, "snapshot": name}


def snapshot_list(serial: str) -> list[str]:
    """Snapshot names known to the running emulator.

    The console prints a table whose ID column is `--` on current emulator builds
    and an integer on older ones, so both are accepted:

        ID        TAG                 VM SIZE                DATE     VM CLOCK
        --        default_boot           458M 2026-08-26 20:26:32  211:41:03.770
    """
    raw = _snapshot_cmd(serial, "list")
    names: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line == "OK" or line.startswith(("ID", "List of snapshots", "There are no")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        is_row = parts[0].isdigit() or set(parts[0]) == {"-"}
        if is_row and set(parts[1]) != {"-"}:
            names.append(parts[1])
    return names
