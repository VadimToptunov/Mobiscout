"""Coverage for the pure utility helpers: identifier/name/filename sanitizing,
and path + project-structure validation. These underpin codegen and I/O, so
their behaviour is pinned here
(including the leading-digit handling that now matches the documented intent).
"""

from pathlib import Path

import pytest

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
