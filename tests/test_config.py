"""Config discovery, defaults, and the errors a typo should produce."""

from __future__ import annotations

from pathlib import Path

import pytest

from android_driver import config as config_mod

SAMPLE = """
app:
  package: com.example.myapp
  activity: .MainActivity
build:
  command: ./gradlew :app:assembleDebug
  apk_glob: app/build/outputs/apk/debug/*.apk
install:
  strategy: reinstall
  appops: [CAMERA]
timing:
  cold_start_settle_s: 3.5
driver:
  backend: adb
"""


def write(tmp_path: Path, text: str, name: str = ".android-driver.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_every_section(tmp_path):
    cfg = config_mod.load(write(tmp_path, SAMPLE))
    assert cfg.app.package == "com.example.myapp"
    assert cfg.build.apk_glob.endswith("*.apk")
    assert cfg.install.strategy == "reinstall"
    assert cfg.install.appops == ["CAMERA"]
    assert cfg.timing.cold_start_settle_s == 3.5
    assert cfg.driver.backend == "adb"
    assert cfg.project_root == tmp_path
    assert cfg.runs_dir == tmp_path / "runs"


def test_defaults_are_the_safe_ones(tmp_path):
    cfg = config_mod.load(write(tmp_path, "app:\n  package: com.x\n"))
    assert cfg.install.strategy == "uninstall-then-install"
    assert cfg.install.grant_runtime_perms is True
    assert cfg.driver.backend == "auto"


def test_no_config_file_still_yields_a_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(tmp_path))
    cfg = config_mod.load()
    assert cfg.source is None
    assert cfg.app.package is None


def test_discovery_walks_up_from_a_subdirectory(tmp_path, monkeypatch):
    write(tmp_path, SAMPLE)
    nested = tmp_path / "app" / "src" / "main"
    nested.mkdir(parents=True)
    monkeypatch.setenv("ANDROID_DRIVER_PROJECT", str(nested))
    assert config_mod.find_config_file() == tmp_path / ".android-driver.yaml"


def test_missing_package_error_says_how_to_fix_it(tmp_path):
    cfg = config_mod.load(write(tmp_path, "build:\n  apk: x.apk\n"))
    with pytest.raises(config_mod.ConfigError, match="app:\n    package:"):
        _ = cfg.package


@pytest.mark.parametrize(
    "text, message",
    [
        ("app:\n  packge: com.x\n", "unknown key"),
        ("nonsense:\n  a: 1\n", "unknown top-level key"),
        ("install:\n  strategy: yolo\n", "install.strategy must be"),
        ("driver:\n  backend: appium\n", "driver.backend must be"),
        ("app: not-a-mapping\n", "must be a mapping"),
        ("- a\n- b\n", "top level must be a mapping"),
        ("app:\n  package: [\n", "invalid YAML"),
    ],
)
def test_bad_config_is_rejected_with_a_useful_message(tmp_path, text, message):
    with pytest.raises(config_mod.ConfigError, match=message):
        config_mod.load(write(tmp_path, text))
