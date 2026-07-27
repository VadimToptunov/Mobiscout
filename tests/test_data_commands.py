"""Behaviour tests for the ``data`` CLI group (test-data generation/management).

Each command is driven end-to-end through CliRunner over tmp_path files, asserting
the real side effects: JSON written, records generated/merged/filtered/sampled and
the structural-validation verdicts. Guards against a re-break of the file plumbing
or the generator wiring silently producing nothing.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.data_commands import data


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    """A command may exit non-zero but must never raise an unexpected exception."""
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _write_json(path: Path, obj) -> str:
    path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("data_type", ["user", "product", "transaction", "card", "address"])
def test_generate_writes_requested_count(runner, tmp_path, data_type):
    out = tmp_path / "out.json"
    result = runner.invoke(
        data,
        ["generate", "-t", data_type, "-c", "7", "-o", str(out), "--seed", "42"],
    )
    _no_crash(result)
    assert result.exit_code == 0, result.output
    assert out.exists()
    records = json.loads(out.read_text())
    assert isinstance(records, list) and len(records) == 7
    # Every record is a non-empty dict (a real generated dataclass, not None).
    assert all(isinstance(r, dict) and r for r in records)


def test_generate_seed_is_reproducible(runner, tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    for out in (a, b):
        runner.invoke(data, ["generate", "-t", "user", "-c", "5", "-o", str(out), "-s", "123"])
    # Same seed -> identical seed-derived fields (ids/names/emails). The only
    # non-deterministic field is metadata.created_at (wall clock), so drop it.
    ids_a = [(r["id"], r["email"], r["date_of_birth"]) for r in json.loads(a.read_text())]
    ids_b = [(r["id"], r["email"], r["date_of_birth"]) for r in json.loads(b.read_text())]
    assert ids_a == ids_b


def test_generate_rejects_unknown_type(runner, tmp_path):
    # click.Choice rejects the value before our callback runs.
    result = runner.invoke(data, ["generate", "-t", "spaceship", "-o", str(tmp_path / "x.json")])
    assert result.exit_code != 0
    assert "Invalid value" in result.output or "spaceship" in result.output


def test_inspect_reports_fields_and_count(runner, tmp_path):
    src = _write_json(tmp_path / "d.json", [{"name": "a", "age": 1}, {"name": "b", "age": 2}])
    result = runner.invoke(data, ["inspect", src])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Records: 2" in result.output
    assert "name" in result.output and "age" in result.output


def test_inspect_rejects_non_array(runner, tmp_path):
    src = _write_json(tmp_path / "d.json", {"not": "a list"})
    result = runner.invoke(data, ["inspect", src])
    _no_crash(result)
    assert result.exit_code != 0  # click.Abort


def test_merge_concatenates_all_records(runner, tmp_path):
    f1 = _write_json(tmp_path / "f1.json", [{"i": 1}, {"i": 2}])
    f2 = _write_json(tmp_path / "f2.json", [{"i": 3}])
    out = tmp_path / "merged.json"
    result = runner.invoke(data, ["merge", f1, f2, "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    merged = json.loads(out.read_text())
    assert [r["i"] for r in merged] == [1, 2, 3]


def test_merge_wraps_single_object_file(runner, tmp_path):
    f1 = _write_json(tmp_path / "obj.json", {"i": 1})
    out = tmp_path / "merged.json"
    result = runner.invoke(data, ["merge", f1, "-o", str(out)])
    _no_crash(result)
    assert json.loads(out.read_text()) == [{"i": 1}]


def test_filter_keeps_only_matching_records(runner, tmp_path):
    src = _write_json(
        tmp_path / "d.json",
        [{"status": "active"}, {"status": "pending"}, {"status": "active"}],
    )
    out = tmp_path / "f.json"
    result = runner.invoke(data, ["filter-data", src, "-f", "status", "-v", "active", "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    filtered = json.loads(out.read_text())
    assert len(filtered) == 2 and all(r["status"] == "active" for r in filtered)


def test_sample_returns_subset_of_requested_size(runner, tmp_path):
    src = _write_json(tmp_path / "d.json", [{"i": i} for i in range(20)])
    out = tmp_path / "s.json"
    result = runner.invoke(data, ["sample", src, "-n", "5", "-o", str(out), "-s", "1"])
    _no_crash(result)
    assert result.exit_code == 0
    sampled = json.loads(out.read_text())
    assert len(sampled) == 5
    # Sampled records are a real subset of the source.
    source_indices = set(range(20))
    assert all(r["i"] in source_indices for r in sampled)


def test_sample_size_larger_than_data_is_rejected(runner, tmp_path):
    src = _write_json(tmp_path / "d.json", [{"i": 1}])
    out = tmp_path / "s.json"
    result = runner.invoke(data, ["sample", src, "-n", "100", "-o", str(out)])
    _no_crash(result)
    assert result.exit_code != 0
    assert not out.exists()


def test_validate_flags_inconsistent_structure(runner, tmp_path):
    src = _write_json(tmp_path / "d.json", [{"a": 1, "b": 2}, {"a": 1}])  # second row misses "b"
    result = runner.invoke(data, ["validate", src])
    _no_crash(result)
    assert "inconsistent" in result.output.lower()


def test_validate_passes_consistent_structure(runner, tmp_path):
    src = _write_json(tmp_path / "d.json", [{"a": 1, "b": 2}, {"a": 3, "b": 4}])
    result = runner.invoke(data, ["validate", src])
    _no_crash(result)
    assert result.exit_code == 0
    assert "consistent structure" in result.output.lower()


def test_validate_rejects_non_array(runner, tmp_path):
    src = _write_json(tmp_path / "d.json", {"a": 1})
    result = runner.invoke(data, ["validate", src])
    _no_crash(result)
    assert result.exit_code != 0
