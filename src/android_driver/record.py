"""Screen recording via `screenrecord`.

The device-side process is started detached and stopped with SIGINT rather than
being killed: `screenrecord` only writes the MP4 moov atom when it shuts down
cleanly, and a SIGKILLed recording leaves a file no player will open. That is
why this goes through a device-side PID instead of the simpler
`Popen(["adb", "shell", "screenrecord", ...])` — a local kill does not reliably
reach the remote process at all.

`screenrecord` caps a single clip at 3 minutes and does not capture on some
emulator GPU configurations; both show up as an empty or missing file, which
`stop()` reports rather than hiding.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import adb
from .log import log

REMOTE_DIR = "/sdcard"
MAX_TIME_LIMIT_S = 180


class RecordError(RuntimeError):
    pass


class Recorder:
    def __init__(self) -> None:
        self.active: dict[str, Any] | None = None

    def start(
        self,
        serial: str,
        *,
        name: str | None = None,
        bit_rate_mbps: float = 4.0,
        size: str | None = None,
        time_limit_s: int = MAX_TIME_LIMIT_S,
    ) -> dict[str, Any]:
        if self.active is not None:
            raise RecordError(
                f"already recording to {self.active['remote']}; call `record_stop` first"
            )
        if time_limit_s > MAX_TIME_LIMIT_S:
            log("record", f"screenrecord caps clips at {MAX_TIME_LIMIT_S}s; clamping {time_limit_s}s")
            time_limit_s = MAX_TIME_LIMIT_S

        stem = name or f"record-{int(time.time())}"
        remote = f"{REMOTE_DIR}/android-driver-{stem}.mp4"
        opts = f"--bit-rate {int(bit_rate_mbps * 1_000_000)} --time-limit {time_limit_s}"
        if size:
            opts += f" --size {size}"
        # nohup + & keeps it alive after this adb shell exits; `echo $!` hands
        # back the device-side PID we need in order to SIGINT it later.
        result = adb.shell_result(
            serial, f"nohup screenrecord {opts} {remote} >/dev/null 2>&1 & echo $!", timeout=30
        )
        pid = result["stdout"].strip().split()[-1] if result["stdout"].strip() else ""
        if not pid.isdigit():
            raise RecordError(
                f"could not start screenrecord on {serial}: {result['stdout']} {result['stderr']}".strip()
            )
        self.active = {"serial": serial, "remote": remote, "pid": int(pid), "started": time.monotonic()}
        log("record", f"recording {serial} → {remote} (pid {pid})")
        return {"remote_path": remote, "pid": int(pid), "time_limit_s": time_limit_s}

    def stop(self, dest: Path) -> dict[str, Any]:
        if self.active is None:
            raise RecordError("not recording — call `record_start` first")
        state, self.active = self.active, None
        serial, remote, pid = state["serial"], state["remote"], state["pid"]

        adb.shell_result(serial, f"kill -2 {pid}", timeout=30)
        self._await_finalized(serial, remote)

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        pull = adb.run(serial, "pull", remote, str(dest), check=False, timeout=180)
        adb.shell_result(serial, f"rm -f {remote}", timeout=30)

        if not dest.is_file() or dest.stat().st_size == 0:
            raise RecordError(
                f"screenrecord produced no usable file (adb pull said: {pull.strip()}). "
                "Some emulator GPU modes cannot capture; try `-gpu swiftshader_indirect`."
            )
        return {
            "path": str(dest),
            "bytes": dest.stat().st_size,
            "seconds": round(time.monotonic() - state["started"], 1),
        }

    @staticmethod
    def _await_finalized(serial: str, remote: str, timeout_s: float = 15.0) -> None:
        """Wait for the file size to stop growing — the moov atom is written last."""
        deadline = time.monotonic() + timeout_s
        last = -1
        while time.monotonic() < deadline:
            time.sleep(0.5)
            out = adb.shell_result(serial, f"stat -c %s {remote} 2>/dev/null || echo 0")["stdout"]
            try:
                size = int(out.strip().splitlines()[-1])
            except (ValueError, IndexError):
                size = 0
            if size and size == last:
                return
            last = size
        log("record", f"{remote} was still changing after {timeout_s}s; pulling anyway")
