"""Coverage for the shared code-quality helpers (dedup utilities): JSON I/O,
statistics/grouping, path validation, the ResultCollector, the retry decorator,
the handle_errors context manager, and ProgressTracker. Previously 0% covered.
"""

import pytest

from framework.core.exceptions import (
    FileAccessError,
    FileNotFoundError as CustomFileNotFoundError,
    SerializationError,
)
from framework.utils.code_quality import (
    ProgressTracker,
    ResultCollector,
    calculate_statistics,
    ensure_directory,
    group_by,
    handle_errors,
    print_summary,
    read_json_file,
    retry_on_error,
    validate_directory,
    validate_file_exists,
    write_json_file,
)

# --- JSON I/O ---------------------------------------------------------------


def test_json_round_trip_pretty_and_compact(tmp_path):
    data = {"a": 1, "unicode": "ключ"}
    pretty = tmp_path / "sub" / "p.json"
    write_json_file(pretty, data, pretty=True)
    assert read_json_file(pretty) == data
    assert "\n" in pretty.read_text()  # pretty is indented

    compact = tmp_path / "c.json"
    write_json_file(compact, data, pretty=False)
    assert read_json_file(compact) == data


def test_read_json_missing_raises_custom(tmp_path):
    with pytest.raises(CustomFileNotFoundError):
        read_json_file(tmp_path / "nope.json")


def test_read_json_invalid_raises_serialization(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(SerializationError):
        read_json_file(bad)


def test_write_json_non_serializable_raises(tmp_path):
    with pytest.raises(SerializationError):
        write_json_file(tmp_path / "x.json", {"bad": {1, 2}})  # a set isn't JSON


def test_ensure_directory_returns_path(tmp_path):
    d = tmp_path / "a" / "b"
    assert ensure_directory(d) == d
    assert d.is_dir()


# --- data processing --------------------------------------------------------


def test_calculate_statistics_empty():
    assert calculate_statistics([]) == {"count": 0, "total": 0, "min": None, "max": None, "avg": None}


def test_calculate_statistics_numeric_key():
    stats = calculate_statistics([{"n": 2}, {"n": 4}, {"n": 6}], key=lambda x: x["n"])
    assert stats == {"count": 3, "total": 12, "min": 2, "max": 6, "avg": 4.0}


def test_calculate_statistics_count_only_without_key():
    assert calculate_statistics([1, 2, 3]) == {"count": 3}


def test_calculate_statistics_non_numeric_key_falls_back_to_count():
    # A key that yields non-comparable/None values degrades to just the count.
    assert calculate_statistics([{"n": None}], key=lambda x: x["n"]) == {"count": 1}


def test_group_by():
    items = [{"k": "a", "v": 1}, {"k": "b", "v": 2}, {"k": "a", "v": 3}]
    groups = group_by(items, key=lambda x: x["k"])
    assert set(groups) == {"a", "b"}
    assert [i["v"] for i in groups["a"]] == [1, 3]


# --- validation -------------------------------------------------------------


def test_validate_file_exists(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    validate_file_exists(f)  # no raise
    with pytest.raises(CustomFileNotFoundError):
        validate_file_exists(tmp_path / "missing")


def test_validate_directory(tmp_path):
    validate_directory(tmp_path)  # no raise
    with pytest.raises(CustomFileNotFoundError):
        validate_directory(tmp_path / "missing")
    f = tmp_path / "f.txt"
    f.write_text("x")
    with pytest.raises(FileAccessError):
        validate_directory(f)  # exists but is a file


# --- ResultCollector --------------------------------------------------------


def test_result_collector():
    rc = ResultCollector()
    assert not rc.has_errors() and not rc.has_warnings()
    rc.add_success("ok")
    rc.add_error(ValueError("boom"))
    rc.add_warning("careful")
    assert rc.has_errors() and rc.has_warnings()
    assert rc.get_summary() == {"success_count": 1, "error_count": 1, "warning_count": 1, "total": 2}


def test_print_summary_hides_underscored_and_expands_dicts(capsys):
    print_summary("Report", {"visible": 1, "_hidden": 2, "nested": {"x": 9}}, verbose=False)
    out = capsys.readouterr().out
    assert "Report" in out
    assert "visible: 1" in out
    assert "_hidden" not in out  # underscore-prefixed hidden unless verbose
    assert "x: 9" in out  # nested dict expanded


# --- retry_on_error ---------------------------------------------------------


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    @retry_on_error(max_attempts=3, delay_seconds=0, retriable_errors=(ValueError,))
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "done"

    assert flaky() == "done"
    assert calls["n"] == 3


def test_retry_reraises_non_retriable_immediately():
    calls = {"n": 0}

    @retry_on_error(max_attempts=3, delay_seconds=0, retriable_errors=(ValueError,))
    def boom():
        calls["n"] += 1
        raise KeyError("not retriable")

    with pytest.raises(KeyError):
        boom()
    assert calls["n"] == 1  # not retried


def test_retry_exhausts_and_raises_last():
    @retry_on_error(max_attempts=2, delay_seconds=0, retriable_errors=(ValueError,))
    def always():
        raise ValueError("still failing")

    with pytest.raises(ValueError):
        always()


# --- handle_errors context manager ------------------------------------------


def test_handle_errors_collects_and_reraises():
    with pytest.raises(RuntimeError):
        with handle_errors("op", raise_on_error=True) as results:
            raise RuntimeError("boom")
    # collector recorded the error before re-raising (checked via swallow variant below)


def test_handle_errors_can_swallow():
    with handle_errors("op", raise_on_error=False) as results:
        raise RuntimeError("boom")
    assert results.has_errors()


def test_handle_errors_success_path():
    with handle_errors("op") as results:
        results.add_success(1)
    assert not results.has_errors()
    assert results.get_summary()["success_count"] == 1


# --- ProgressTracker --------------------------------------------------------


def test_progress_tracker(capsys):
    tracker = ProgressTracker(total=2, description="Work")
    tracker.update()
    tracker.update()
    out = capsys.readouterr().out
    assert "Work" in out and "2/2" in out and "100.0%" in out


def test_progress_tracker_finish_and_zero_total(capsys):
    ProgressTracker(total=0).update()  # no ZeroDivisionError
    tracker = ProgressTracker(total=5)
    tracker.finish()
    assert tracker.current == 5
