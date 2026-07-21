"""The `project generate` orchestration lives in a service layer so model loading
and suite emission are testable without a terminal. These drive it against a tmp
project and a small in-memory app model."""

from pathlib import Path

import pytest
import yaml

from framework.cli.generate_service import (
    GenerateServiceError,
    generate_suite,
    load_app_model,
)
from framework.model.app_model import AppModel

_MODEL = {
    "meta": {
        "schema_version": "1.0.0",
        "app_version": "1.0",
        "platform": "android",
        "recorded_at": "2026-07-21T00:00:00",
    },
    "screens": {
        "home_screen": {
            "id": "home_screen",
            "name": "Home Screen",
            "elements": [
                {
                    "id": "login_button",
                    "type": "button",
                    "selector": {"android": "id/login", "test_id": "login"},
                    "capabilities": ["tappable"],
                }
            ],
        }
    },
    "api_calls": {},
    "flows": [],
}


def _write_model(tmp_path: Path, data=None) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    model_path = cfg / "app_model.yaml"
    model_path.write_text(yaml.safe_dump(data if data is not None else _MODEL), encoding="utf-8")
    return model_path


# --- load_app_model ---------------------------------------------------------


def test_load_app_model_returns_a_validated_model(tmp_path):
    model = load_app_model(_write_model(tmp_path))
    assert isinstance(model, AppModel)
    assert "home_screen" in model.screens


def test_load_app_model_defaults_a_missing_meta_block(tmp_path):
    bare = {"screens": {}}
    model = load_app_model(_write_model(tmp_path, bare))
    assert model.meta is not None  # a default meta was injected


def test_load_app_model_raises_on_missing_file(tmp_path):
    with pytest.raises(GenerateServiceError) as ei:
        load_app_model(tmp_path / "config" / "nope.yaml")
    assert "not found" in str(ei.value).lower()


def test_load_app_model_raises_on_invalid_yaml(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    bad = cfg / "app_model.yaml"
    bad.write_text("screens: [unclosed\n", encoding="utf-8")
    with pytest.raises(GenerateServiceError) as ei:
        load_app_model(bad)
    assert "YAML" in str(ei.value)


# --- generate_suite ---------------------------------------------------------


@pytest.fixture()
def model(tmp_path):
    return load_app_model(_write_model(tmp_path))


def test_generate_suite_writes_page_objects_and_integration_tests(tmp_path, model):
    report = generate_suite(
        model,
        tmp_path,
        generate_page_objects=True,
        generate_tests=True,
        generate_api_tests=False,
        generate_features=False,
    )
    assert report.stats["page_objects"] >= 1
    assert report.stats["tests"] >= 1
    assert (tmp_path / "page_objects").is_dir()
    test_files = list((tmp_path / "tests" / "integration").glob("test_*.py"))
    assert test_files
    # The emitted integration test is valid Python for the Page Object it targets.
    source = test_files[0].read_text()
    compile(source, str(test_files[0]), "exec")
    assert "class TestHomeScreen" in source
    assert not report.nothing_generated


def test_generate_suite_skips_disabled_steps(tmp_path, model):
    report = generate_suite(
        model,
        tmp_path,
        generate_page_objects=False,
        generate_tests=False,
        generate_api_tests=False,
        generate_features=False,
    )
    assert report.nothing_generated
    assert report.steps == []
    assert not (tmp_path / "page_objects").exists()


def test_generate_suite_reports_steps_for_the_command_to_narrate(tmp_path, model):
    report = generate_suite(
        model,
        tmp_path,
        generate_page_objects=True,
        generate_tests=False,
        generate_api_tests=False,
        generate_features=False,
    )
    assert [s.title for s in report.steps] == ["Generating Page Objects"]
    assert report.steps[0].items  # named the files it wrote
