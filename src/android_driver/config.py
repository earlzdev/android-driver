"""Project configuration: `.android-driver.yaml` discovery, parsing, defaults.

Everything app-specific lives in the *consumer's* repo, never in this package.
The file is optional — with no config at all the server still exposes every
generic tool; only `build_app` and the recipe tools need it.

Discovery walks up from `$ANDROID_DRIVER_PROJECT` (or the process cwd) looking for
`.android-driver.yaml` / `.android_driver.yml` / `android_driver.yaml`. The directory
holding the file becomes `project_root`, and every relative path in the config
resolves against it — so `apk_glob` and `command` behave the same no matter
which directory the MCP client happened to launch us from.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .log import log

CONFIG_NAMES = (".android-driver.yaml", ".android-driver.yml", "android-driver.yaml", "android-driver.yml")


class ConfigError(RuntimeError):
    pass


@dataclass
class AppConfig:
    package: str | None = None
    activity: str | None = None


@dataclass
class BuildConfig:
    command: str | None = None
    apk_glob: str | None = None
    apk: str | None = None
    timeout_s: int = 900


@dataclass
class InstallConfig:
    # "uninstall-then-install" is the default for a reason: debug APKs built from
    # different branches carry different signing keys, and `pm install -r` then
    # fails with INSTALL_FAILED_UPDATE_INCOMPATIBLE. Reinstall is offered for
    # projects that deliberately want to preserve app data across installs.
    strategy: str = "uninstall-then-install"
    grant_runtime_perms: bool = True
    appops: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        allowed = {"uninstall-then-install", "reinstall"}
        if self.strategy not in allowed:
            raise ConfigError(f"install.strategy must be one of {sorted(allowed)}, got {self.strategy!r}")


@dataclass
class TimingConfig:
    # Cold-start settle before the first UI query. Compose recomposition after a
    # long idle regularly takes seconds on slower hardware; undersleeping races
    # the first tap and produces "element not found" on a screen that is fine.
    cold_start_settle_s: float = 2.0
    # Post-click settle. Many Compose buttons render as android.view.View with
    # clickable=false in the accessibility tree, so a fast follow-up query hits
    # pre-animation state and misses the screen that is currently transitioning in.
    click_settle_s: float = 0.25
    boot_timeout_s: int = 300
    default_find_timeout_s: int = 10


@dataclass
class DriverConfig:
    # "auto" prefers uiautomator2 and silently falls back to the pure-adb driver
    # when u2 is unavailable (not installed, or the device-side agent is missing).
    backend: str = "auto"

    def __post_init__(self) -> None:
        allowed = {"auto", "uiautomator2", "adb"}
        if self.backend not in allowed:
            raise ConfigError(f"driver.backend must be one of {sorted(allowed)}, got {self.backend!r}")


@dataclass
class Config:
    project_root: Path
    source: Path | None
    app: AppConfig = field(default_factory=AppConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    install: InstallConfig = field(default_factory=InstallConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    driver: DriverConfig = field(default_factory=DriverConfig)
    recipes: dict[str, Any] = field(default_factory=dict)
    selectors: dict[str, Any] = field(default_factory=dict)
    runs_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.runs_dir = self.project_root / "runs"

    @property
    def package(self) -> str:
        """The configured package, or raise a message that says how to fix it."""
        if not self.app.package:
            raise ConfigError(
                "no app package configured. Either pass `pkg=` explicitly, or add to "
                f"{self.source or (self.project_root / CONFIG_NAMES[0])}:\n"
                "  app:\n    package: com.example.myapp"
            )
        return self.app.package


# Directories never worth descending into when looking for a config.
_SKIP_DIRS = {"build", ".git", ".gradle", ".idea", "node_modules", "venv", ".venv", "__pycache__"}


def find_config_file(start: Path | None = None) -> Path | None:
    """Find the project config: walk up from `start`, then look a short way down.

    Walking up is the normal case. The downward pass exists because the app under
    test is often *not* at the directory the client was opened in — a repo whose
    Android app lives in `app/` or `test_app/` is completely ordinary, and without
    it every tool fails with "no app package configured" while a perfectly good
    config sits one level below. Ambiguity is refused rather than guessed at.
    """
    here = (start or Path(os.environ.get("ANDROID_DRIVER_PROJECT", "."))).expanduser().resolve()
    if here.is_file():
        here = here.parent
    for candidate in [here, *here.parents]:
        for name in CONFIG_NAMES:
            path = candidate / name
            if path.is_file():
                return path
    return find_config_below(here)


def find_config_below(root: Path, max_depth: int = 3) -> Path | None:
    """The single config beneath `root`, or None when there is no single answer."""
    found: list[Path] = []
    for depth in range(1, max_depth + 1):
        for name in CONFIG_NAMES:
            for path in root.glob("/".join(["*"] * depth + [name])):
                if path.is_file() and not any(part in _SKIP_DIRS for part in path.parts):
                    found.append(path)
        if found:
            break
    if len(found) == 1:
        log("config", f"no config at {root}; using the one below it: {found[0]}")
        return found[0]
    if found:
        log(
            "config",
            f"{len(found)} configs below {root} and none at it: {[str(p) for p in sorted(found)]}. "
            "Set ANDROID_DRIVER_PROJECT to the one you mean.",
        )
    return None


def _section(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key) or {}
    if not isinstance(value, dict):
        raise ConfigError(f"config section {key!r} must be a mapping, got {type(value).__name__}")
    return value


def _build_dataclass(cls: type, raw: dict[str, Any], section: str):
    known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"unknown key(s) in config section {section!r}: {sorted(unknown)}")
    return cls(**raw)


def load(path: Path | None = None) -> Config:
    """Load the project config, falling back to an all-defaults config when absent."""
    source = path or find_config_file()
    if source is None:
        root = Path(os.environ.get("ANDROID_DRIVER_PROJECT", ".")).expanduser().resolve()
        log("config", f"no config file found; using defaults with project_root={root}")
        return Config(project_root=root, source=None)

    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{source}: invalid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: top level must be a mapping, got {type(raw).__name__}")

    known_top = {"app", "build", "install", "timing", "driver", "recipes", "selectors"}
    unknown_top = set(raw) - known_top
    if unknown_top:
        raise ConfigError(f"{source}: unknown top-level key(s): {sorted(unknown_top)}")

    cfg = Config(
        project_root=source.parent,
        source=source,
        app=_build_dataclass(AppConfig, _section(raw, "app"), "app"),
        build=_build_dataclass(BuildConfig, _section(raw, "build"), "build"),
        install=_build_dataclass(InstallConfig, _section(raw, "install"), "install"),
        timing=_build_dataclass(TimingConfig, _section(raw, "timing"), "timing"),
        driver=_build_dataclass(DriverConfig, _section(raw, "driver"), "driver"),
        recipes=_section(raw, "recipes"),
        selectors=_section(raw, "selectors"),
    )
    log("config", f"loaded {source} (package={cfg.app.package}, recipes={len(cfg.recipes)})")
    return cfg
