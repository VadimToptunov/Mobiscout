"""Behaviour tests for the ``ml`` CLI group (element-classifier training/prediction).

A small, balanced, hand-labelled dataset is trained for real (RandomForest), the
resulting .pkl is loaded back for ``evaluate`` and ``predict``, and the app-model
-> training-data extractor runs over a real JSON model. Nothing is mocked: these
drive the actual sklearn pipeline. Error branches (empty/invalid inputs) are
covered too.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.ml_commands import ml

# Three element types, 10 samples each: enough for the stratified split + 5-fold CV.
_TEMPLATES = {
    "button": {"class": "android.widget.Button", "clickable": True, "text": "OK"},
    "input": {"class": "android.widget.EditText", "clickable": True, "text": ""},
    "image": {"class": "android.widget.ImageView", "clickable": False, "text": ""},
}


def _training_rows():
    rows = []
    for label, base in _TEMPLATES.items():
        for i in range(10):
            row = dict(base)
            row["label"] = label
            row["bounds"] = {"x": i, "y": i, "width": 100 + i, "height": 40}
            rows.append(row)
    return rows


def _test_rows():
    return [
        {"features": dict(base, bounds={"x": 1, "y": 1, "width": 100, "height": 40}), "element_type": label}
        for label, base in _TEMPLATES.items()
    ]


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


@pytest.fixture()
def trained_model(runner, tmp_path) -> Path:
    """Train a real model once and hand back its .pkl path."""
    train_file = tmp_path / "train.json"
    train_file.write_text(json.dumps(_training_rows()), encoding="utf-8")
    model = tmp_path / "model.pkl"
    result = runner.invoke(ml, ["train", "-t", str(train_file), "-o", str(model)])
    _no_crash(result)
    assert result.exit_code == 0, result.output
    assert model.exists()
    return model


def test_train_produces_model_and_reports_accuracy(runner, tmp_path):
    train_file = tmp_path / "train.json"
    train_file.write_text(json.dumps(_training_rows()), encoding="utf-8")
    model = tmp_path / "sub" / "model.pkl"  # parent dir must be created by the command

    result = runner.invoke(ml, ["train", "-t", str(train_file), "-o", str(model), "--test-split", "0.2"])
    _no_crash(result)
    assert result.exit_code == 0
    assert model.exists()
    assert "Accuracy" in result.output and "Model trained" in result.output


def test_train_invalid_json_aborts(runner, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    result = runner.invoke(ml, ["train", "-t", str(bad), "-o", str(tmp_path / "m.pkl")])
    _no_crash(result)
    assert result.exit_code != 0
    assert "Training failed" in result.output


def test_evaluate_reports_accuracy(runner, tmp_path, trained_model):
    test_file = tmp_path / "test.json"
    test_file.write_text(json.dumps(_test_rows()), encoding="utf-8")
    result = runner.invoke(ml, ["evaluate", "-m", str(trained_model), "-t", str(test_file)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Overall Accuracy" in result.output


def test_predict_from_json_string(runner, trained_model):
    result = runner.invoke(ml, ["predict", "-m", str(trained_model), "-e", json.dumps(_TEMPLATES["button"])])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Type: button" in result.output
    assert "Confidence" in result.output


def test_predict_from_file(runner, tmp_path, trained_model):
    element_file = tmp_path / "el.json"
    element_file.write_text(json.dumps(_TEMPLATES["input"]), encoding="utf-8")
    result = runner.invoke(ml, ["predict", "-m", str(trained_model), "-e", str(element_file)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Type: input" in result.output


def test_predict_invalid_json_aborts(runner, trained_model):
    result = runner.invoke(ml, ["predict", "-m", str(trained_model), "-e", "{not json"])
    _no_crash(result)
    assert result.exit_code != 0
    assert "Invalid JSON" in result.output


def test_generate_training_data_from_app_model(runner, tmp_path):
    app_model = {
        "screens": [
            {
                "name": "Login",
                "elements": [
                    {"class": "android.widget.Button", "clickable": True, "text": "Sign in"},
                    {"class": "android.widget.EditText", "clickable": True, "text": ""},
                ],
            }
        ]
    }
    model_file = tmp_path / "model.json"
    model_file.write_text(json.dumps(app_model), encoding="utf-8")
    out = tmp_path / "training.json"

    result = runner.invoke(ml, ["generate-training-data", "-a", str(model_file), "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()
    rows = json.loads(out.read_text())
    assert len(rows) == 2
    # Each extracted element was labelled with an inferred element_type.
    assert all("element_type" in row for row in rows)


def test_import_rico_extracts_and_writes_rows(runner, tmp_path):
    # A minimal RICO semantic-annotation file: bounds are [x1, y1, x2, y2] and the
    # role lives in componentLabel.
    rico_dir = tmp_path / "rico"
    rico_dir.mkdir()
    (rico_dir / "0.json").write_text(
        json.dumps(
            {
                "componentLabel": "Toolbar",  # container -> skipped
                "bounds": [0, 0, 1000, 100],
                "children": [
                    {"componentLabel": "Text Button", "bounds": [0, 0, 200, 80], "clickable": True},
                    {"componentLabel": "Input", "bounds": [0, 100, 400, 180]},
                    {"componentLabel": "Image", "bounds": [0, 200, 100, 300]},
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "rows.json"
    result = runner.invoke(ml, ["import-rico", "--rico-dir", str(rico_dir), "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert out.exists()
    rows = json.loads(out.read_text())
    labels = {r["label"] for r in rows}
    # Mapped leaf roles are extracted; the Toolbar container is not.
    assert labels == {"button", "input", "image"}


def test_import_rico_empty_dir_aborts(runner, tmp_path):
    empty = tmp_path / "rico"
    empty.mkdir()
    result = runner.invoke(ml, ["import-rico", "--rico-dir", str(empty)])
    _no_crash(result)
    assert result.exit_code != 0
    assert "No labelled rows" in result.output
