"""Visual regression used to compare *file sizes* as a proxy — meaningless (two
different images of equal size scored 0% diff). It now does a real per-pixel
comparison via Pillow. These build actual images and pin the behaviour.
"""

from PIL import Image

from framework.analysis.visual_analyzer import VisualAnalyzer


def _solid(path, color, size=(20, 20)):
    Image.new("RGB", size, color).save(path)
    return path


def _analyzer(tmp_path):
    base = tmp_path / "baseline"
    base.mkdir()
    return VisualAnalyzer(base), base


def test_identical_images_are_a_match(tmp_path):
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 255, 255))
    cur = _solid(tmp_path / "home.png", (255, 255, 255))
    diff = va.compare_screenshots("home", cur)
    assert diff is not None
    assert diff.diff_percentage == 0.0
    assert diff.is_match
    assert diff.diff_regions == []


def test_completely_different_images_are_a_regression(tmp_path):
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 255, 255))  # white baseline
    cur = _solid(tmp_path / "home.png", (0, 0, 0))  # black current
    diff = va.compare_screenshots("home", cur)
    assert diff.diff_percentage > 90  # ~100%, from real pixels
    assert diff.has_regression
    assert diff.diff_regions  # bounding box of the change


def test_same_size_but_different_is_not_scored_zero(tmp_path):
    # The old file-size proxy scored equal-sized-but-different images as 0%.
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 0, 0), size=(20, 20))
    cur = _solid(tmp_path / "home.png", (0, 0, 255), size=(20, 20))  # same size, different
    diff = va.compare_screenshots("home", cur)
    assert diff.diff_percentage > 0


def test_partial_change_bounding_box(tmp_path):
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 255, 255), size=(20, 20))
    cur_img = Image.new("RGB", (20, 20), (255, 255, 255))
    for x in range(5):
        for y in range(5):
            cur_img.putpixel((x, y), (0, 0, 0))  # a 5x5 black square in the corner
    cur = tmp_path / "home.png"
    cur_img.save(cur)
    diff = va.compare_screenshots("home", cur)
    assert 0 < diff.diff_percentage < 50
    assert diff.diff_regions == [(0, 0, 5, 5)]
