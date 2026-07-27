"""Behaviour tests for the visual analyzer's baseline / batch / reporting paths
(framework/analysis/visual_analyzer.py).

Complements test_visual_analyzer_real.py (which pins the per-pixel diff maths):
here we use real PNGs via Pillow to drive baseline creation, missing-image
handling, batch comparison, and the text + HTML + exported-image reports.
"""

from PIL import Image

from framework.analysis.visual_analyzer import VisualAnalyzer, VisualDiff


def _solid(path, color, size=(10, 10)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def _analyzer(tmp_path):
    base = tmp_path / "baseline"
    base.mkdir()
    return VisualAnalyzer(base), base


# --- VisualDiff dataclass properties ----------------------------------------


def test_visual_diff_properties():
    diff = VisualDiff(
        screen_name="home",
        baseline_image=None,
        current_image=None,
        diff_percentage=5.0,
        diff_regions=[(0, 0, 5, 5)],
        threshold=0.01,  # 1%
    )
    assert diff.has_regression  # 5% > 1%
    assert not diff.is_match
    assert diff.similarity_score == 0.95


def test_visual_diff_within_threshold_is_match():
    diff = VisualDiff("s", None, None, diff_percentage=0.5, diff_regions=[], threshold=0.01)
    assert not diff.has_regression
    assert diff.is_match


# --- baseline handling -------------------------------------------------------


def test_missing_baseline_creates_it_and_returns_none(tmp_path):
    va, base = _analyzer(tmp_path)
    cur = _solid(tmp_path / "cur" / "home.png", (10, 20, 30))
    result = va.compare_screenshots("home", cur)
    assert result is None
    # Baseline was created by copying the current image.
    assert (base / "home.png").exists()


def test_missing_current_image_returns_none(tmp_path):
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 255, 255))
    result = va.compare_screenshots("home", tmp_path / "does_not_exist.png")
    assert result is None


def test_update_baseline_overwrites(tmp_path):
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 255, 255))
    new = _solid(tmp_path / "new.png", (0, 0, 0))
    va.update_baseline("home", new)
    # Now the baseline is black; comparing black-vs-black matches.
    cur = _solid(tmp_path / "cur.png", (0, 0, 0))
    diff = va.compare_screenshots("home", cur)
    assert diff.is_match


# --- batch_compare -----------------------------------------------------------


def test_batch_compare_collects_only_regressions(tmp_path):
    va, base = _analyzer(tmp_path)
    _solid(base / "match.png", (255, 255, 255))
    _solid(base / "regress.png", (255, 255, 255))

    shots = tmp_path / "shots"
    shots.mkdir()
    _solid(shots / "match.png", (255, 255, 255))  # identical -> no regression
    _solid(shots / "regress.png", (0, 0, 0))  # very different -> regression

    regressions = va.batch_compare(shots)
    names = {d.screen_name for d in regressions}
    assert names == {"regress"}
    assert va.diffs  # regression stored on the analyzer


# --- reports -----------------------------------------------------------------


def test_generate_report_no_regressions(tmp_path):
    va, _ = _analyzer(tmp_path)
    report = va.generate_report()
    assert "No visual regressions detected." in report


def test_generate_report_lists_regressions(tmp_path):
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 255, 255))
    cur = _solid(tmp_path / "home.png", (0, 0, 0))
    va.compare_screenshots("home", cur)
    report = va.generate_report()
    assert "Found 1 visual regression(s)" in report
    assert "Screen: home" in report
    assert "Difference:" in report
    assert "Changed regions: 1" in report


def test_generate_html_report_writes_file(tmp_path):
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 255, 255))
    cur = _solid(tmp_path / "home.png", (0, 0, 0))
    va.compare_screenshots("home", cur)

    out = tmp_path / "out" / "report.html"
    va.generate_html_report(out)
    html = out.read_text()
    assert "<title>Visual Regression Report</title>" in html
    assert "home" in html
    assert "Total screens: 1" in html
    assert "FAILED" in html  # black-vs-white is a failed diff


def test_export_diff_images_copies_current(tmp_path):
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 255, 255))
    cur = _solid(tmp_path / "home.png", (0, 0, 0))
    va.compare_screenshots("home", cur)

    out = tmp_path / "diffs"
    va.export_diff_images(out)
    assert (out / "home_diff.png").exists()
