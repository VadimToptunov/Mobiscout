"""`mobiscout ml import-rico` — wires the previously-unreachable RICO extractor
(framework/ml/rico_extractor) into the live ML training pipeline. The extractor's
own docstring says its output "is merged into the shipped real_elements.json", but
nothing did that merge until this command. These tests drive it end-to-end over a
tiny synthetic RICO annotation tree.
"""

import json

import pytest
from click.testing import CliRunner

from framework.cli.ml_commands import ml
from framework.ml import real_data_extractor

# One RICO semantic-annotation screen: a Text Button (-> button) and a Text (-> text).
_RICO_SCREEN = {
    "componentLabel": "Root",
    "bounds": [0, 0, 1080, 1920],
    "children": [
        {
            "componentLabel": "Text Button",
            "class": "android.widget.Button",
            "clickable": True,
            "bounds": [0, 0, 200, 80],
        },
        {"componentLabel": "Text", "class": "android.widget.TextView", "bounds": [0, 100, 300, 140]},
        {"componentLabel": "Toolbar", "class": "android.widget.Toolbar", "bounds": [0, 0, 1080, 100]},  # skipped
    ],
}


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def rico_dir(tmp_path):
    d = tmp_path / "rico"
    d.mkdir()
    (d / "1.json").write_text(json.dumps(_RICO_SCREEN), encoding="utf-8")
    return d


def test_import_rico_writes_rows(runner, rico_dir, tmp_path):
    out = tmp_path / "rows.json"
    result = runner.invoke(ml, ["import-rico", "--rico-dir", str(rico_dir), "--output", str(out)])
    assert result.exit_code == 0, result.output
    rows = json.loads(out.read_text())
    labels = sorted(r["label"] for r in rows)
    assert labels == ["button", "text"]  # Toolbar (chrome) was skipped


def test_import_rico_merge_shipped(runner, rico_dir, tmp_path, monkeypatch):
    # Redirect the shipped dataset to a temp file so the test never touches the
    # real bundled data.
    shipped = tmp_path / "real_elements.json"
    monkeypatch.setattr(real_data_extractor, "SHIPPED_DATASET", shipped)

    result = runner.invoke(ml, ["import-rico", "--rico-dir", str(rico_dir), "--merge-shipped"])
    assert result.exit_code == 0, result.output
    assert shipped.exists()
    merged = json.loads(shipped.read_text())
    assert {r["label"] for r in merged} == {"button", "text"}

    # Merging again is idempotent (exact-duplicate rows are dropped).
    runner.invoke(ml, ["import-rico", "--rico-dir", str(rico_dir), "--merge-shipped"])
    assert len(json.loads(shipped.read_text())) == len(merged)


def test_import_rico_empty_dir_aborts(runner, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(ml, ["import-rico", "--rico-dir", str(empty)])
    assert result.exit_code != 0  # click.Abort — no rows extracted
