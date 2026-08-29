"""Run bundles: every artifact from one test attempt, in one directory.

An agent that finds a bug and then cannot show you *why* it believes that has
done half the work. A run collects the evidence as it goes — a timeline of every
action with its timing, a screenshot and hierarchy dump at each failure, and the
logcat slice for exactly that window — and writes a report a human can read
without replaying anything.

Artifacts are captured even with no run open: they land under
`runs/failures/<timestamp>/` instead. A failure you have to reproduce in order
to collect evidence for is a failure you have already half lost.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import adb
from .config import Config
from .log import log
from .session import Session

_SLUG_OK = "abcdefghijklmnopqrstuvwxyz0123456789-_"


def _slug(value: str, limit: int = 40) -> str:
    cleaned = "".join(c if c in _SLUG_OK else "-" for c in value.strip().lower())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:limit] or "run"


@dataclass
class Event:
    t: float
    tool: str
    status: str
    duration_s: float
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": round(self.t, 3),
            "tool": self.tool,
            "status": self.status,
            "duration_s": self.duration_s,
            **({"detail": self.detail} if self.detail else {}),
        }


class Run:
    """One test attempt and the directory holding its evidence."""

    def __init__(self, root: Path, name: str, note: str = "") -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.name = name
        self.note = note
        self.id = f"{stamp}-{_slug(name)}"
        self.dir = root / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.started_at = time.time()
        self.started_mono = time.monotonic()
        self.events: list[Event] = []
        self.device: dict[str, str] = {}
        self.recording: dict[str, Any] | None = None
        self.finished = False

    # ── recording events ─────────────────────────────────────────────────────

    def event(self, tool: str, status: str, duration_s: float, detail: dict[str, Any] | None = None) -> Event:
        ev = Event(
            t=time.monotonic() - self.started_mono,
            tool=tool,
            status=status,
            duration_s=round(duration_s, 3),
            detail=detail or {},
        )
        self.events.append(ev)
        return ev

    def artifact(self, name: str) -> Path:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def failures(self) -> list[Event]:
        return [e for e in self.events if e.status != "ok"]

    # ── output ───────────────────────────────────────────────────────────────

    def write_timeline(self) -> Path:
        payload = {
            "id": self.id,
            "name": self.name,
            "note": self.note,
            "started_at": self.started_at,
            "duration_s": round(time.monotonic() - self.started_mono, 2),
            "device": self.device,
            "recording": self.recording,
            "events": [e.to_dict() for e in self.events],
        }
        path = self.dir / "timeline.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def write_report(self) -> Path:
        total = time.monotonic() - self.started_mono
        failures = self.failures
        lines = [
            f"# Run {self.id}",
            "",
            f"- **name**: {self.name}",
            f"- **started**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.started_at))}",
            f"- **duration**: {total:.1f}s",
            f"- **steps**: {len(self.events)} ({len(failures)} failed)",
        ]
        if self.note:
            lines.append(f"- **note**: {self.note}")
        for key in ("serial", "model", "android_version", "sdk", "screen"):
            if self.device.get(key):
                lines.append(f"- **{key}**: {self.device[key]}")
        if self.recording:
            lines.append(f"- **recording**: `{self.recording.get('path', '?')}`")

        lines += ["", "## Timeline", "", "| t | step | status | took |", "|---:|---|---|---:|"]
        for e in self.events:
            lines.append(f"| {e.t:6.1f}s | `{e.tool}` | {e.status} | {e.duration_s:.2f}s |")

        if failures:
            lines += ["", "## Failures", ""]
            for e in failures:
                lines.append(f"### `{e.tool}` at {e.t:.1f}s")
                lines.append("")
                error = e.detail.get("error")
                if error:
                    lines += ["```", str(error), "```", ""]
                for key in ("screenshot", "hierarchy"):
                    if e.detail.get(key):
                        lines.append(f"- {key}: `{e.detail[key]}`")
                lines.append("")

        lines += ["", "## Artifacts", ""]
        for path in sorted(self.dir.rglob("*")):
            if path.is_file() and path.name != "report.md":
                lines.append(f"- `{path.relative_to(self.dir)}`")

        path = self.dir / "report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def write_logcat(self, serial: str, pkg: str | None) -> Path | None:
        """The log for this run's window. Assumes the buffer was cleared at the start."""
        try:
            lines = adb.logcat_dump(serial, lines=20000, buffers="main,crash")
        except Exception as e:
            log("run", f"could not capture logcat: {e}")
            return None
        path = self.dir / "logcat.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if pkg:
            app_lines = [line for line in lines if pkg in line]
            if app_lines:
                (self.dir / "logcat-app.txt").write_text("\n".join(app_lines) + "\n", encoding="utf-8")
        return path


class Runs:
    """Owns the current run and the fallback artifact directory."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.current: Run | None = None

    @property
    def root(self) -> Path:
        return self.cfg.runs_dir

    def start(self, session: Session, name: str, note: str = "", clear_log: bool = True) -> dict[str, Any]:
        if self.current is not None and not self.current.finished:
            previous = self.current.id
            self.end(session)
            log("run", f"auto-closed the previous run {previous}")
        run = Run(self.root, name, note)
        try:
            run.device = adb.device_info(session.serial)
        except Exception as e:
            log("run", f"could not read device info: {e}")
        if clear_log:
            try:
                adb.logcat_clear(session.serial)
            except Exception as e:
                log("run", f"could not clear logcat: {e}")
        self.current = run
        log("run", f"started {run.id} → {run.dir}")
        return {"run_id": run.id, "dir": str(run.dir)}

    def end(self, session: Session) -> dict[str, Any]:
        run = self.current
        if run is None or run.finished:
            raise RuntimeError("no run is open — call `run_start` first")
        pkg = self.cfg.app.package
        serial = run.device.get("serial") or (session.current_serial or "")
        if serial:
            run.write_logcat(serial, pkg)
        timeline = run.write_timeline()
        report = run.write_report()
        run.finished = True
        self.current = None
        failures = [e.tool for e in run.failures]
        log("run", f"finished {run.id} ({len(run.events)} steps, {len(failures)} failed)")
        return {
            "run_id": run.id,
            "dir": str(run.dir),
            "steps": len(run.events),
            "failed": failures,
            "passed": not failures,
            "report": str(report),
            "timeline": str(timeline),
        }

    # ── artifacts ────────────────────────────────────────────────────────────

    def artifact_dir(self, kind: str = "failures") -> Path:
        if self.current is not None and not self.current.finished:
            return self.current.dir
        path = self.root / kind / time.strftime("%Y%m%d-%H%M%S")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def capture(self, session: Session, tag: str) -> dict[str, str]:
        """Screenshot + hierarchy for post-hoc triage. Never raises."""
        out = self.artifact_dir()
        stamp = f"{tag}-{int(time.time() * 1000) % 100000}"
        captured: dict[str, str] = {}
        png = out / f"{stamp}.png"
        try:
            session.driver.screenshot(png)
            captured["screenshot"] = str(png)
        except Exception as e:
            log("run", f"screenshot capture failed for {tag}: {e}")
        xml = out / f"{stamp}.xml"
        try:
            xml.write_text(session.driver.dump_hierarchy(), encoding="utf-8")
            captured["hierarchy"] = str(xml)
        except Exception as e:
            log("run", f"hierarchy capture failed for {tag}: {e}")
        if not captured:
            # An unreachable device fails both captures; don't leave the empty
            # directory behind to look like evidence that exists.
            for path in (png, xml):
                path.unlink(missing_ok=True)
            if out != getattr(self.current, "dir", None) and not any(out.iterdir()):
                out.rmdir()
        return captured

    def record_event(
        self, tool: str, status: str, duration_s: float, detail: dict[str, Any] | None = None
    ) -> None:
        if self.current is not None and not self.current.finished:
            self.current.event(tool, status, duration_s, detail)

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for path in sorted(self.root.iterdir(), reverse=True):
            timeline = path / "timeline.json"
            if not timeline.is_file():
                continue
            try:
                data = json.loads(timeline.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            failed = [e["tool"] for e in data.get("events", []) if e.get("status") != "ok"]
            out.append(
                {
                    "run_id": data.get("id", path.name),
                    "name": data.get("name", ""),
                    "duration_s": data.get("duration_s"),
                    "steps": len(data.get("events", [])),
                    "failed": failed,
                    "dir": str(path),
                }
            )
            if len(out) >= limit:
                break
        return out
