"""The configuration core: file round-trips, env-var expansion, dot-notation
get/set, discovery, and validation. This module underpins every `mobiscout config`
command and had no tests."""

import json

import pytest

from framework.config.config_manager import ConfigManager, MobiscoutConfig


def test_defaults_are_sane():
    cfg = MobiscoutConfig()
    assert cfg.framework.timeout == 30
    assert cfg.devices.android.adb_timeout == 30
    assert cfg.ml.confidence_threshold == 0.8
    assert cfg.integrations.slack.enabled is False


def test_yaml_round_trip(tmp_path):
    path = tmp_path / "mobiscout.yaml"
    cfg = MobiscoutConfig()
    cfg.set("framework.timeout", 99)
    cfg.set("devices.android.system_port", 8299)
    cfg.to_file(path)

    loaded = MobiscoutConfig.from_file(path)
    assert loaded.get("framework.timeout") == 99
    assert loaded.get("devices.android.system_port") == 8299


def test_json_round_trip(tmp_path):
    path = tmp_path / "mobiscout.json"
    cfg = MobiscoutConfig()
    cfg.set("ml.model_version", "3.1")
    cfg.to_file(path)
    assert json.loads(path.read_text())["ml"]["model_version"] == "3.1"
    assert MobiscoutConfig.from_file(path).get("ml.model_version") == "3.1"


def test_from_file_missing_and_bad_format(tmp_path):
    with pytest.raises(FileNotFoundError):
        MobiscoutConfig.from_file(tmp_path / "nope.yaml")
    bad = tmp_path / "config.txt"
    bad.write_text("x")
    with pytest.raises(ValueError):
        MobiscoutConfig.from_file(bad)


def test_empty_yaml_yields_defaults(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("")  # yaml.safe_load -> None
    assert MobiscoutConfig.from_file(path).get("framework.timeout") == 30


def test_env_var_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_SLACK", "https://hooks.example/abc")
    path = tmp_path / "c.yaml"
    path.write_text("integrations:\n  slack:\n    webhook_url: ${MY_SLACK}\n    enabled: true\n")
    cfg = MobiscoutConfig.from_file(path)
    assert cfg.get("integrations.slack.webhook_url") == "https://hooks.example/abc"


def test_env_var_unset_left_literal(tmp_path, monkeypatch):
    monkeypatch.delenv("ABSENT_VAR", raising=False)
    path = tmp_path / "c.yaml"
    path.write_text("integrations:\n  github:\n    token: ${ABSENT_VAR}\n")
    # An unset ${VAR} is left as-is rather than blanked.
    assert MobiscoutConfig.from_file(path).get("integrations.github.token") == "${ABSENT_VAR}"


def test_get_missing_key_returns_default():
    cfg = MobiscoutConfig()
    assert cfg.get("framework.does_not_exist", "fallback") == "fallback"
    assert cfg.get("nope.deep.path") is None


def test_set_invalid_key_raises():
    cfg = MobiscoutConfig()
    with pytest.raises(ValueError):
        cfg.set("framework.bogus", 1)
    with pytest.raises(ValueError):
        cfg.set("bogus.path", 1)


def test_manager_missing_path_uses_defaults_then_saves(tmp_path):
    path = tmp_path / ".mobiscout.yaml"
    mgr = ConfigManager(config_path=path)  # file doesn't exist -> defaults
    assert mgr.get("framework.timeout") == 30
    mgr.set("framework.timeout", 45)  # save=True by default
    assert path.exists()
    assert ConfigManager(config_path=path).get("framework.timeout") == 45


def test_manager_discovers_file_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".mobiscout.yaml").write_text("framework:\n  timeout: 7\n")
    mgr = ConfigManager()  # no explicit path -> discovery
    assert mgr.config_path.name == ".mobiscout.yaml"
    assert mgr.get("framework.timeout") == 7


def test_validate_flags_each_bad_field(tmp_path):
    mgr = ConfigManager(config_path=tmp_path / "c.yaml")
    assert mgr.validate() == []  # defaults are valid
    mgr.set("framework.timeout", 0, save=False)
    mgr.set("framework.log_level", "LOUD", save=False)
    mgr.set("ml.confidence_threshold", 2.0, save=False)
    mgr.set("integrations.slack.enabled", True, save=False)
    errors = mgr.validate()
    assert any("framework.timeout" in e for e in errors)
    assert any("log_level" in e for e in errors)
    assert any("confidence_threshold" in e for e in errors)
    assert any("slack.webhook_url" in e for e in errors)


def test_init_default_creates_then_refuses_overwrite(tmp_path):
    path = tmp_path / ".mobiscout.yaml"
    mgr = ConfigManager(config_path=path)
    mgr.init_default()
    assert path.exists()
    with pytest.raises(FileExistsError):
        mgr.init_default()


def test_list_all_returns_full_tree(tmp_path):
    data = ConfigManager(config_path=tmp_path / "c.yaml").list_all()
    assert data["framework"]["timeout"] == 30
    assert "devices" in data and "ml" in data and "integrations" in data
