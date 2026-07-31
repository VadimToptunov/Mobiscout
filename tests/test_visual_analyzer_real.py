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


def test_export_diff_draws_regions_not_just_a_copy(tmp_path):
    """export_diff_images used to just copy the current frame; it must now draw
    the changed regions so a reviewer sees *what* changed. The current image is
    solid black, so any red pixel proves an outline was actually rendered."""
    va, base = _analyzer(tmp_path)
    _solid(base / "home.png", (255, 255, 255), size=(40, 40))  # white baseline
    cur = _solid(tmp_path / "home.png", (0, 0, 0), size=(40, 40))  # black current
    va.compare_screenshots("home", cur)

    out_dir = tmp_path / "diffs"
    va.export_diff_images(out_dir)

    out = out_dir / "home_diff.png"
    assert out.exists()
    with Image.open(out) as img:
        rgb = img.convert("RGB")
        assert rgb.size == (40, 40)  # same frame, annotated
        colors = {c for _, c in rgb.getcolors(maxcolors=4096)}
    # A red outline was drawn onto the black frame (a plain copy would be all black).
    assert any(r > 200 and g < 80 and b < 80 for (r, g, b) in colors)
