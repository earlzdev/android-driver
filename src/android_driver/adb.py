"""Generic ADB wrappers. No project-specific knowledge lives here.

Two behaviours are load-bearing and deliberately not "simplified":

  * `install()` defaults to uninstall-then-install rather than `pm install -r`.
    Debug APKs built from different branches are signed with different debug
    keys, and reinstalling over one with the other fails with
    INSTALL_FAILED_UPDATE_INCOMPATIBLE — a confusing error that costs an
    afternoon the first time you hit it.
  * The permission sweep grants every runtime permission the manifest declares
    and then *verifies* none are still denied, with an OEM `appops` pass for
    skins (MIUI and friends) whose permission overlay can keep blocking an app
    after `pm grant` reports success.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .log import log


class AdbError(RuntimeError):
    pass


# Ops that OEM permission overlays most often keep blocking after a successful
# `pm grant`. Cheap to set, harmless when they do not apply.
OEM_APPOPS = (
    "CAMERA",
    "RECORD_AUDIO",
    "CALL_PHONE",
    "READ_PHONE_STATE",
    "POST_NOTIFICATION",
    "SYSTEM_ALERT_WINDOW",
)

_VERSION_CODE_RE = re.compile(r"versionCode=(\d+)")


def _adb(
    args: list[str], *, check: bool = True, timeout: int | None = 120
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(["adb", *args], check=False, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as e:
        raise AdbError("`adb` not found on PATH. Install Android platform-tools and retry.") from e
    except subprocess.TimeoutExpired as e:
        raise AdbError(f"adb {' '.join(args)} timed out after {timeout}s") from e
    if check and result.returncode != 0:
        raise AdbError(f"adb {' '.join(args)} failed (exit={result.returncode}): {result.stderr.strip()}")
    return result


def run(serial: str, *args: str, check: bool = True, timeout: int | None = 120) -> str:
    return _adb(["-s", serial, *args], check=check, timeout=timeout).stdout


def shell(serial: str, *args: str, check: bool = True, timeout: int | None = 120) -> str:
    return run(serial, "shell", *args, check=check, timeout=timeout)


def shell_result(serial: str, cmd: str, timeout: int | None = 120) -> dict:
    """Run a raw shell command string and return its full result.

    `cmd` is passed as a single argument, so the device-side `sh -c` interprets
    it — pipes, quoting and redirection all work.
    """
    result = _adb(["-s", serial, "shell", cmd], check=False, timeout=timeout)
    return {
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


# ── devices ───────────────────────────────────────────────────────────────────


def list_devices() -> list[dict[str, str]]:
    """Every attached device in state `device`, with its model and AVD name."""
    out = _adb(["devices", "-l"]).stdout
    devices: list[dict[str, str]] = []
    for raw in out.splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        serial = parts[0]
        props = dict(p.split(":", 1) for p in parts[2:] if ":" in p)
        devices.append(
            {
                "serial": serial,
                "model": props.get("model", ""),
                "device": props.get("device", ""),
                "is_emulator": str(serial.startswith("emulator-")),
            }
        )
    return devices


def list_serials() -> list[str]:
    return [d["serial"] for d in list_devices()]


def pick_device() -> str:
    """First serial in state `device`. Emulators win ties — this is android_driver."""
    devices = list_devices()
    if not devices:
        raise AdbError(
            "no adb device in state 'device'. Start an emulator with `start_emulator`, "
            "or check `adb devices` for an unauthorized/offline entry."
        )
    emulators = [d for d in devices if d["is_emulator"] == "True"]
    chosen = (emulators or devices)[0]["serial"]
    if len(devices) > 1:
        others = [d["serial"] for d in devices if d["serial"] != chosen]
        log("adb", f"WARNING: {len(devices)} devices attached; picking {chosen!r}. Others: {others}")
    return chosen


def device_info(serial: str) -> dict[str, str]:
    props = {
        "model": "ro.product.model",
        "manufacturer": "ro.product.manufacturer",
        "android_version": "ro.build.version.release",
        "sdk": "ro.build.version.sdk",
        "abi": "ro.product.cpu.abi",
        "avd_name": "ro.boot.qemu.avd_name",
    }
    info = {"serial": serial}
    for key, prop in props.items():
        info[key] = shell(serial, "getprop", prop, check=False).strip()
    size = shell(serial, "wm", "size", check=False).strip()
    density = shell(serial, "wm", "density", check=False).strip()
    info["screen"] = size.split(":")[-1].strip() if ":" in size else size
    info["density"] = density.split(":")[-1].strip() if ":" in density else density
    return info


# ── app lifecycle ─────────────────────────────────────────────────────────────


def is_installed(serial: str, pkg: str) -> bool:
    out = shell(serial, "pm", "list", "packages", pkg, check=False)
    return any(line.strip() == f"package:{pkg}" for line in out.splitlines())


def app_info(serial: str, pkg: str) -> dict:
    """Version metadata from `dumpsys package`. Prefer this over parsing pm output by hand."""
    if not is_installed(serial, pkg):
        return {"installed": False, "pkg": pkg}
    out = shell(serial, "dumpsys", "package", pkg, check=False)
    info: dict = {
        "installed": True,
        "pkg": pkg,
        "version_name": None,
        "version_code": None,
        "first_install_time": None,
        "last_update_time": None,
        "apk_path": None,
    }
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("versionName="):
            info["version_name"] = line.split("=", 1)[1].strip()
        elif line.startswith("versionCode="):
            m = _VERSION_CODE_RE.search(line)
            if m:
                info["version_code"] = int(m.group(1))
        elif line.startswith("firstInstallTime="):
            info["first_install_time"] = line.split("=", 1)[1].strip()
        elif line.startswith("lastUpdateTime="):
            info["last_update_time"] = line.split("=", 1)[1].strip()
        elif line.startswith("codePath="):
            info["apk_path"] = line.split("=", 1)[1].strip()
    return info


def force_stop(serial: str, pkg: str) -> None:
    shell(serial, "am", "force-stop", pkg)


def clear_data(serial: str, pkg: str) -> None:
    shell(serial, "pm", "clear", pkg)


def pidof(serial: str, pkg: str) -> int | None:
    out = shell(serial, "pidof", pkg, check=False).strip()
    if not out:
        return None
    try:
        return int(out.split()[0])
    except ValueError:
        return None


def launch(serial: str, pkg: str, activity: str | None = None) -> None:
    """Start the app. With no activity, resolve the launcher intent via monkey."""
    if activity:
        component = activity if "/" in activity else f"{pkg}/{activity}"
        shell(serial, "am", "start", "-n", component)
        return
    result = _adb(
        ["-s", serial, "shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"],
        check=False,
    )
    if "No activities found" in (result.stdout + result.stderr):
        raise AdbError(
            f"{pkg} has no launcher activity. Pass an explicit activity, or set "
            "`app.activity` in your config."
        )


def uninstall(serial: str, pkg: str) -> None:
    """Uninstall `pkg`. No-op when it is not installed."""
    if not is_installed(serial, pkg):
        return
    result = _adb(["-s", serial, "uninstall", pkg], check=False)
    combined = (result.stdout + result.stderr).lower()
    benign = ("not installed", "unknown package", "delete_failed_internal_error")
    if result.returncode == 0 or any(s in combined for s in benign):
        return
    raise AdbError(f"uninstall {pkg} on {serial} failed: {result.stdout.strip()} {result.stderr.strip()}")


def declared_permissions(serial: str, pkg: str) -> list[str]:
    out = shell(serial, "dumpsys", "package", pkg, check=False)
    perms: list[str] = []
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("android.permission.") and ":" in line:
            perm = line.split(":", 1)[0].strip()
            if perm not in perms:
                perms.append(perm)
    return perms


def denied_permissions(serial: str, pkg: str) -> list[str]:
    out = shell(serial, "dumpsys", "package", pkg, check=False)
    return [
        line.strip().split(":", 1)[0].strip()
        for line in out.splitlines()
        if line.strip().startswith("android.permission.") and "granted=false" in line
    ]


def grant(serial: str, pkg: str, perm: str) -> None:
    """Grant a runtime permission. Install-time perms produce a benign error we swallow."""
    result = _adb(["-s", serial, "shell", "pm", "grant", pkg, perm], check=False)
    if result.returncode == 0:
        return
    combined = (result.stdout + result.stderr).lower()
    if "not a changeable permission" in combined or "not a runtime" in combined:
        return
    raise AdbError(f"pm grant {perm} on {serial} failed: {result.stdout.strip()} {result.stderr.strip()}")


def set_appops(serial: str, pkg: str, ops: tuple[str, ...] | list[str] = OEM_APPOPS) -> None:
    """Force-allow app ops that OEM permission overlays keep blocking after `pm grant`."""
    for op in ops:
        shell(serial, "appops", "set", pkg, op, "allow", check=False)


def _install_apk(serial: str, apk: Path) -> None:
    result = _adb(["-s", serial, "install", "-g", "-t", str(apk)], check=False, timeout=600)
    combined = result.stdout + result.stderr
    if result.returncode != 0 or "Success" not in combined:
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in combined:
            raise AdbError(
                f"install {apk.name} failed: signature mismatch with the installed copy. "
                "Set `install.strategy: uninstall-then-install` (the default) in your config."
            )
        raise AdbError(f"install {apk.name} on {serial} failed: {combined.strip()}")


def install(
    serial: str,
    apk_path: str | Path,
    pkg: str,
    *,
    strategy: str = "uninstall-then-install",
    grant_runtime_perms: bool = True,
    appops: list[str] | None = None,
) -> dict:
    """Full install cycle: stop → (uninstall) → install → grant → verify."""
    apk = Path(apk_path).expanduser().resolve()
    if not apk.is_file():
        raise AdbError(f"APK not found: {apk}")

    force_stop(serial, pkg)
    if strategy == "uninstall-then-install":
        uninstall(serial, pkg)
    _install_apk(serial, apk)

    granted: list[str] = []
    if grant_runtime_perms:
        for perm in declared_permissions(serial, pkg):
            grant(serial, pkg, perm)
            granted.append(perm)
        set_appops(serial, pkg, appops or OEM_APPOPS)
        still_denied = denied_permissions(serial, pkg)
        if still_denied:
            raise AdbError(
                f"runtime permissions still denied after the grant sweep: {still_denied}. "
                f"Fix manually: adb -s {serial} shell pm grant {pkg} <perm>"
            )
    return {"apk_path": str(apk), "pkg": pkg, "granted_permissions": granted}


# ── logcat ────────────────────────────────────────────────────────────────────


def logcat_clear(serial: str) -> None:
    _adb(["-s", serial, "logcat", "-c"], check=False)


def logcat_dump(
    serial: str,
    *,
    lines: int | None = 2000,
    pkg: str | None = None,
    pattern: str | None = None,
    level: str | None = None,
    buffers: str | None = None,
) -> list[str]:
    """Snapshot the log buffer. `pkg` filters by live PID; `pattern` is a regex.

    `buffers` maps to `logcat -b` — pass "main,crash" to catch native aborts and
    tombstones, which never reach the default buffer. Note that `pkg` resolves to
    a *live* PID, so it silently matches nothing once the process has died; leave
    it unset when you are looking for the crash that killed it.
    """
    args = ["-s", serial, "logcat", "-d"]
    if buffers:
        args += ["-b", buffers]
    if lines:
        args += ["-t", str(lines)]
    if pkg:
        pid = pidof(serial, pkg)
        if pid is not None:
            args += [f"--pid={pid}"]
    if level:
        args += ["*:" + level.upper()[0]]
    out = _adb(args, check=False, timeout=60).stdout
    result = out.splitlines()
    if pattern:
        rx = re.compile(pattern)
        result = [line for line in result if rx.search(line)]
    return result
