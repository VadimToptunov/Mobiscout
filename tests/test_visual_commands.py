"""Behaviour tests for the ``visual`` CLI group (visual regression testing).

Uses real PNG fixtures written with Pillow so the underlying per-pixel diff runs
for real: identical images pass, a changed image is reported as a regression (and
exits non-zero). Baseline capture/approve/list/delete/reset are exercised over
tmp_path directories, asserting the files that land on disk.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner
from PIL import Image

from framework.cli.visual_commands import visual


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _png(path: Path, color=(255, 255, 255), size=(40, 40)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def test_capture_copies_screenshots_as_baselines(runner, tmp_path):
    shots = tmp_path / "shots"
    _png(shots / "home.png")
    _png(shots / "login.png")
    out = tmp_path / "baselines"
    result = runner.invoke(visual, ["capture", "-s", str(shots), "-o", str(out)])
    _no_crash(result)
    assert result.exit_code == 0
    assert (out / "home.png").exists() and (out / "login.png").exists()


def test_capture_errors_when_no_screenshots(runner, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(visual, ["capture", "-s", str(empty), "-o", str(tmp_path / "b")])
    _no_crash(result)
    assert result.exit_code != 0


def test_compare_passes_for_identical_images(runner, tmp_path):
    baseline = tmp_path / "baselines"
    current = tmp_path / "current"
    _png(baseline / "home.png", (10, 20, 30))
    _png(current / "home.png", (10, 20, 30))  # identical

    result = runner.invoke(visual, ["compare", "-b", str(baseline), "-c", str(current), "-t", "0.01"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Passed" in result.output


def test_compare_detects_regression(runner, tmp_path):
    baseline = tmp_path / "baselines"
    current = tmp_path / "current"
    _png(baseline / "home.png", (0, 0, 0))  # black baseline
    _png(current / "home.png", (255, 255, 255))  # white current -> big diff

    result = runner.invoke(visual, ["compare", "-b", str(baseline), "-c", str(current), "-t", "0.01"])
    _no_crash(result)
    # Regression -> click.Abort -> non-zero exit.
    assert result.exit_code != 0
    assert "Regression" in result.output


def test_compare_missing_baseline_dir_aborts(runner, tmp_path):
    current = tmp_path / "current"
    _png(current / "home.png")
    result = runner.invoke(visual, ["compare", "-b", str(tmp_path / "nope"), "-c", str(current)])
    _no_crash(result)
    assert result.exit_code != 0
    assert "Baseline directory not found" in result.output


def test_compare_creates_missing_baseline(runner, tmp_path):
    baseline = tmp_path / "baselines"
    baseline.mkdir()
    current = tmp_path / "current"
    _png(current / "brand_new.png")

    result = runner.invoke(visual, ["compare", "-b", str(baseline), "-c", str(current)])
    _no_crash(result)
    assert "No baseline" in result.output
    # The analyzer auto-creates the missing baseline.
    assert (baseline / "brand_new.png").exists()


def test_approve_overwrites_baseline(runner, tmp_path):
    baseline = tmp_path / "baselines"
    _png(baseline / "home.png", (0, 0, 0))
    new_shot = _png(tmp_path / "new.png", (255, 255, 255))

    result = runner.invoke(visual, ["approve", "home", "-b", str(baseline), "-c", str(new_shot)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Overwriting existing baseline" in result.output
    # Baseline now matches the freshly approved (white) image.
    assert Image.open(baseline / "home.png").convert("RGB").getpixel((0, 0)) == (255, 255, 255)


def test_list_baselines_shows_entries(runner, tmp_path):
    baseline = tmp_path / "baselines"
    _png(baseline / "home.png")
    _png(baseline / "cart.png")
    result = runner.invoke(visual, ["list-baselines", "-b", str(baseline)])
    _no_crash(result)
    assert "home" in result.output and "cart" in result.output


def test_list_baselines_no_directory(runner, tmp_path):
    result = runner.invoke(visual, ["list-baselines", "-b", str(tmp_path / "missing")])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No baselines directory" in result.output


def test_delete_removes_named_baseline(runner, tmp_path):
    baseline = tmp_path / "baselines"
    _png(baseline / "home.png")
    result = runner.invoke(visual, ["delete", "home", "-b", str(baseline)], input="y\n")
    _no_crash(result)
    assert result.exit_code == 0
    assert not (baseline / "home.png").exists()


def test_delete_missing_baseline_aborts(runner, tmp_path):
    baseline = tmp_path / "baselines"
    baseline.mkdir()
    result = runner.invoke(visual, ["delete", "ghost", "-b", str(baseline)], input="y\n")
    _no_crash(result)
    assert result.exit_code != 0


def test_reset_deletes_all_baselines(runner, tmp_path):
    baseline = tmp_path / "baselines"
    _png(baseline / "a.png")
    _png(baseline / "b.png")
    result = runner.invoke(visual, ["reset", "-b", str(baseline)], input="y\n")
    _no_crash(result)
    assert result.exit_code == 0
    assert list(baseline.glob("*.png")) == []


def test_config_info_reports_counts(runner, tmp_path):
    baseline = tmp_path / "baselines"
    _png(baseline / "a.png")
    result = runner.invoke(visual, ["config-info", "-b", str(baseline), "-t", "0.05"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Baselines count: 1" in result.output
    assert "5.0%" in result.output
