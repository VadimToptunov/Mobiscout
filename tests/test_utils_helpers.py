"""Coverage for the pure utility helpers: identifier/name/filename sanitizing,
path + project-structure validation, and the safe file/JSON/YAML round-trips.
These modules underpin codegen and I/O, so their behaviour is pinned here
(including the leading-digit handling that now matches the documented intent).
"""

import json
from pathlib import Path

import pytest
import yaml

from framework.utils.file_utils import (
    ensure_directory,
    load_json,
    load_yaml,
    safe_read_file,
    safe_write_file,
    save_json,
    save_yaml,
)
from framework.utils.sanitizer import sanitize_class_name, sanitize_filename, sanitize_identifier
from framework.utils.validator import (
    ValidationError,
    validate_android_project,
    validate_ios_project,
    validate_output_format,
    validate_path,
    validate_project_structure,
)

# --- sanitizer --------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("My Screen", "my_screen"),
        ("api-client", "api_client"),
        ("Button!", "button"),
        ("  spaced  ", "__spaced__"),  # spaces -> underscores; not trimmed
        ("123-invalid", "invalid_123"),  # leading digits moved to the end, not dropped
        ("007agent", "agent_007"),
        ("123", "item"),  # all digits -> default (nothing left to lead with)
        ("", "item"),  # empty -> default
        ("!!!", "item"),  # nothing valid -> default
        ("class", "class_"),  # python keyword gets a trailing underscore
        ("for", "for_"),
    ],
)
def test_sanitize_identifier(raw, expected):
    assert sanitize_identifier(raw) == expected


def test_sanitize_identifier_custom_default():
    assert sanitize_identifier("", default="thing") == "thing"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("home screen", "HomeScreen"),
        ("api-client", "ApiClient"),
        ("already_snake_case", "AlreadySnakeCase"),
        ("123Test", "Test123"),  # leading digits moved to the end
        ("42", "Item"),  # all digits -> default
        ("", "Item"),
    ],
)
def test_sanitize_class_name(raw, expected):
    assert sanitize_class_name(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("My File.txt", "my_file"),  # extension stripped, spaces -> underscore
        ("Test/File", "test_file"),
        ("a---b___c", "a---b_c"),  # only underscore runs collapse (hyphens kept)
        ("__edge__", "edge"),  # leading/trailing underscores stripped
        ("", "file"),
        ("...", "file"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


# --- validator --------------------------------------------------------------


def test_validate_path_returns_resolved_path(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert validate_path(f, must_exist=True, must_be_file=True) == f.resolve()


def test_validate_path_missing_raises(tmp_path):
    with pytest.raises(ValidationError):
        validate_path(tmp_path / "nope", must_exist=True)


def test_validate_path_wrong_kind_raises(tmp_path):
    with pytest.raises(ValidationError):
        validate_path(tmp_path, must_be_file=True)  # a dir, not a file
    f = tmp_path / "f.txt"
    f.write_text("x")
    with pytest.raises(ValidationError):
        validate_path(f, must_be_dir=True)  # a file, not a dir


def test_validate_path_create_if_missing(tmp_path):
    target = tmp_path / "made"
    out = validate_path(target, must_exist=True, must_be_dir=True, create_if_missing=True)
    assert out.is_dir()


def test_validate_project_structure_reports_missing(tmp_path):
    (tmp_path / "setup.py").write_text("")
    (tmp_path / "src").mkdir()
    ok, missing = validate_project_structure(
        tmp_path, required_files=["setup.py", "README.md"], required_dirs=["src", "tests"]
    )
    assert not ok
    assert any("README.md" in m for m in missing)
    assert any("tests" in m for m in missing)


def test_validate_project_structure_all_present(tmp_path):
    (tmp_path / "setup.py").write_text("")
    ok, missing = validate_project_structure(tmp_path, required_files=["setup.py"])
    assert ok and missing == []


def test_validate_project_structure_bad_root():
    ok, missing = validate_project_structure(Path("/definitely/not/here"))
    assert not ok and missing


def test_validate_android_project_gradle_and_kts(tmp_path):
    ok, missing = validate_android_project(tmp_path)
    assert not ok  # nothing there yet
    (tmp_path / "build.gradle.kts").write_text("")
    (tmp_path / "settings.gradle.kts").write_text("")
    (tmp_path / "app" / "src").mkdir(parents=True)
    ok, missing = validate_android_project(tmp_path)
    assert ok and missing == []


def test_validate_ios_project(tmp_path):
    ok, missing = validate_ios_project(tmp_path)
    assert not ok and missing
    (tmp_path / "App.xcodeproj").mkdir()
    ok, missing = validate_ios_project(tmp_path)
    assert ok and missing == []


def test_validate_output_format():
    assert validate_output_format("JSON", ["json", "yaml"]) == "json"
    with pytest.raises(ValidationError):
        validate_output_format("xml", ["json", "yaml"])


# --- file_utils -------------------------------------------------------------


def test_safe_read_write_round_trip(tmp_path):
    f = tmp_path / "sub" / "note.txt"
    assert safe_write_file(f, "héllo", create_dirs=True) is True
    assert safe_read_file(f) == "héllo"


def test_safe_read_missing_returns_none(tmp_path):
    assert safe_read_file(tmp_path / "missing.txt") is None


def test_json_round_trip_and_bad_input(tmp_path):
    f = tmp_path / "d" / "data.json"
    data = {"a": 1, "ключ": [1, 2, 3]}
    assert save_json(f, data) is True
    assert load_json(f) == data
    assert load_json(tmp_path / "missing.json") is None
    # invalid JSON on disk -> None, not a raise
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid")
    assert load_json(bad) is None


def test_save_json_non_serializable_returns_false(tmp_path):
    assert save_json(tmp_path / "x.json", {"bad": {1, 2, 3}}) is False  # set isn't JSON


def test_yaml_round_trip_and_bad_input(tmp_path):
    f = tmp_path / "d" / "data.yaml"
    data = {"name": "démo", "items": [1, 2]}
    assert save_yaml(f, data) is True
    assert load_yaml(f) == data
    assert load_yaml(tmp_path / "missing.yaml") is None
    bad = tmp_path / "bad.yaml"
    bad.write_text("key: : :\n  - broken\n:::")
    assert load_yaml(bad) is None


def test_ensure_directory(tmp_path):
    d = tmp_path / "a" / "b" / "c"
    assert ensure_directory(d) is True
    assert d.is_dir()
    assert ensure_directory(d) is True  # idempotent


def test_written_json_is_readable_by_stdlib(tmp_path):
    f = tmp_path / "o.json"
    save_json(f, {"k": "v"})
    assert json.loads(f.read_text()) == {"k": "v"}


def test_written_yaml_is_readable_by_pyyaml(tmp_path):
    f = tmp_path / "o.yaml"
    save_yaml(f, {"k": "v"})
    assert yaml.safe_load(f.read_text()) == {"k": "v"}
