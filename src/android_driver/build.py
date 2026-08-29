"""Building the app under test.

Fully generic: the project config supplies a shell command and a glob for the
resulting artifact, so this works for Gradle, Bazel, a Makefile, or a script.
`build.apk` short-circuits everything for projects that ship a prebuilt binary.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config
from .log import log


class BuildError(RuntimeError):
    pass


def resolve_apk(cfg: Config, path: str | None = None) -> Path:
    """Return an APK to install without building: explicit arg, then config, then glob."""
    if path:
        apk = Path(path).expanduser()
        apk = apk if apk.is_absolute() else cfg.project_root / apk
        if not apk.is_file():
            raise BuildError(f"APK not found: {apk}")
        return apk.resolve()
    if cfg.build.apk:
        apk = Path(cfg.build.apk).expanduser()
        apk = apk if apk.is_absolute() else cfg.project_root / apk
        if not apk.is_file():
            raise BuildError(f"build.apk is set but the file does not exist: {apk}")
        return apk.resolve()
    return find_apk(cfg)


def find_apk(cfg: Config) -> Path:
    if not cfg.build.apk_glob:
        raise BuildError(
            "no APK to install. Add one of these to your config:\n"
            "  build:\n    apk: path/to/app.apk\n"
            "  # or, to build from source:\n"
            "  build:\n    command: ./gradlew :app:assembleDebug\n"
            "    apk_glob: app/build/outputs/apk/debug/*.apk"
        )
    matches = sorted(cfg.project_root.glob(cfg.build.apk_glob))
    if not matches:
        raise BuildError(f"no APK matched {cfg.build.apk_glob!r} under {cfg.project_root}")
    if len(matches) > 1:
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        log("build", f"WARNING: {len(matches)} APKs matched {cfg.build.apk_glob!r}; picking {matches[0]}")
    return matches[0].resolve()


def build(cfg: Config) -> Path:
    """Run the configured build command and return the artifact it produced."""
    if cfg.build.apk and not cfg.build.command:
        return resolve_apk(cfg)
    if not cfg.build.command:
        raise BuildError(
            "no build.command configured. Add it to your config, or call "
            "`install_app` with an explicit apk path."
        )

    log("build", f"running: {cfg.build.command} (cwd={cfg.project_root})")
    result = subprocess.run(
        cfg.build.command,
        shell=True,
        cwd=str(cfg.project_root),
        text=True,
        capture_output=True,
        check=False,
        timeout=cfg.build.timeout_s,
    )
    if result.returncode != 0:
        # Build output is the whole diagnostic value here, so pass it through
        # rather than making the agent go hunting for a log file.
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-60:])
        raise BuildError(f"build failed (exit={result.returncode}):\n{tail}")
    return find_apk(cfg)
