"""VisualDetector does OpenCV/OCR-backed screenshot analysis: image similarity
(MSE / histogram / SSIM-with-MSE-fallback), template matching, visual-regression
diffing and region extraction. These build real images on disk and pin the
numeric behaviour. skimage is not installed here, so the SSIM path exercises its
documented MSE fallback. OCR is exercised through pytesseract, whose engine call
is stubbed (the tesseract binary is not present) and whose absence branch is
covered by toggling the availability flag.

Guards a real fix: the MSE metric used to subtract uint8 arrays, overflowing so
that wholly-different images scored as near-identical; it now widens to int32.
"""

import numpy as np
import pytest

from framework.ml import visual_detector as vd
from framework.ml.visual_detector import VisualDetector


# --------------------------------------------------------------------------- #
# Image helpers (write BGR arrays the way cv2.imread will read them back)
# --------------------------------------------------------------------------- #
def _solid(path, value, size=(40, 40)):
    import cv2

    img = np.full((size[1], size[0], 3), value, dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return path


def _noise(path, size=(100, 100), seed=0):
    """A random-but-deterministic image; unique enough for exact template match."""
    import cv2

    rng = np.random.default_rng(seed)
    img = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return img


# --------------------------------------------------------------------------- #
# calculate_image_similarity
# --------------------------------------------------------------------------- #
def test_mse_identical_images_score_one(tmp_path):
    a = _solid(tmp_path / "a.png", 128)
    b = _solid(tmp_path / "b.png", 128)
    assert VisualDetector().calculate_image_similarity(a, b, method="mse") == 1.0


def test_mse_opposite_images_score_zero(tmp_path):
    # Regression guard: with the uint8 overflow bug this returned ~1.0.
    white = _solid(tmp_path / "w.png", 255)
    black = _solid(tmp_path / "k.png", 0)
    sim = VisualDetector().calculate_image_similarity(white, black, method="mse")
    assert sim == pytest.approx(0.0, abs=1e-6)


def test_histogram_identical_images_score_one(tmp_path):
    a = _solid(tmp_path / "a.png", 200)
    b = _solid(tmp_path / "b.png", 200)
    sim = VisualDetector().calculate_image_similarity(a, b, method="histogram")
    assert sim == pytest.approx(1.0, abs=1e-6)


def test_ssim_falls_back_to_mse_when_skimage_missing(tmp_path):
    # skimage is not installed in this env, so ssim delegates to mse -> 1.0.
    a = _solid(tmp_path / "a.png", 50)
    b = _solid(tmp_path / "b.png", 50)
    assert VisualDetector().calculate_image_similarity(a, b, method="ssim") == 1.0


def test_different_sized_images_are_resized_before_compare(tmp_path):
    a = _solid(tmp_path / "a.png", 77, size=(60, 40))
    b = _solid(tmp_path / "b.png", 77, size=(30, 20))  # same colour, different size
    sim = VisualDetector().calculate_image_similarity(a, b, method="mse")
    assert sim == 1.0


def test_unknown_method_raises(tmp_path):
    a = _solid(tmp_path / "a.png", 10)
    b = _solid(tmp_path / "b.png", 10)
    with pytest.raises(ValueError):
        VisualDetector().calculate_image_similarity(a, b, method="bogus")


def test_missing_image_raises_value_error(tmp_path):
    a = _solid(tmp_path / "a.png", 10)
    with pytest.raises(ValueError):
        VisualDetector().calculate_image_similarity(a, tmp_path / "nope.png", method="mse")


# --------------------------------------------------------------------------- #
# detect_visual_changes
# --------------------------------------------------------------------------- #
def test_detect_visual_changes_identical(tmp_path):
    base = _solid(tmp_path / "base.png", 120)
    cur = _solid(tmp_path / "cur.png", 120)
    has_changes, similarity, diff = VisualDetector().detect_visual_changes(base, cur)
    assert has_changes is False
    assert similarity == 1.0
    assert diff is None


def test_detect_visual_changes_regression_produces_diff(tmp_path):
    base = _solid(tmp_path / "base.png", 255)
    cur = _solid(tmp_path / "cur.png", 0)
    has_changes, similarity, diff = VisualDetector().detect_visual_changes(base, cur)
    assert has_changes is True
    assert similarity < 0.95
    assert isinstance(diff, np.ndarray)
    assert diff.shape == (40, 40, 3)


def test_save_visual_diff_writes_file(tmp_path):
    diff = np.zeros((10, 10, 3), dtype=np.uint8)
    out = tmp_path / "nested" / "diff.png"
    VisualDetector().save_visual_diff(diff, out)
    assert out.exists()


# --------------------------------------------------------------------------- #
# Template matching: find_element_by_image
# --------------------------------------------------------------------------- #
def test_find_element_by_image_locates_template(tmp_path):
    import cv2

    img = _noise(tmp_path / "shot.png", seed=1)
    # Cut a distinctive patch at (col=30, row=40), 20x20, and save as template.
    patch = img[40:60, 30:50]
    cv2.imwrite(str(tmp_path / "tpl.png"), patch)

    box = VisualDetector().find_element_by_image(tmp_path / "shot.png", tmp_path / "tpl.png", threshold=0.8)
    assert box == (30, 40, 20, 20)


def test_find_element_by_image_no_match_returns_none(tmp_path):
    _noise(tmp_path / "shot.png", seed=2)
    _noise(tmp_path / "tpl.png", size=(20, 20), seed=999)  # unrelated content
    box = VisualDetector().find_element_by_image(tmp_path / "shot.png", tmp_path / "tpl.png", threshold=0.99)
    assert box is None


def test_find_element_by_image_missing_file_returns_none(tmp_path):
    _noise(tmp_path / "shot.png", seed=3)
    box = VisualDetector().find_element_by_image(tmp_path / "shot.png", tmp_path / "missing.png")
    assert box is None


# --------------------------------------------------------------------------- #
# find_similar_elements / find_similar_by_bounds
# --------------------------------------------------------------------------- #
def test_find_similar_elements_returns_confident_match(tmp_path):
    import cv2

    img = _noise(tmp_path / "shot.png", seed=4)
    cv2.imwrite(str(tmp_path / "tpl.png"), img[40:60, 30:50])

    matches = VisualDetector().find_similar_elements(
        tmp_path / "shot.png", tmp_path / "tpl.png", threshold=0.7, max_results=5
    )
    assert matches, "expected at least one match"
    x, y, w, h, conf = matches[0]
    assert (x, y, w, h) == (30, 40, 20, 20)
    assert conf > 0.99
    assert len(matches) <= 5


def test_find_similar_elements_missing_file_returns_empty(tmp_path):
    _noise(tmp_path / "shot.png", seed=5)
    assert VisualDetector().find_similar_elements(tmp_path / "shot.png", tmp_path / "missing.png") == []


def test_find_similar_by_bounds_returns_dicts(tmp_path):
    _noise(tmp_path / "shot.png", seed=6)
    results = VisualDetector().find_similar_by_bounds(tmp_path / "shot.png", (30, 40, 20, 20), 0.7, max_results=3)
    assert results
    top = results[0]
    assert top["x"] == 30 and top["y"] == 40
    assert top["width"] == 20 and top["height"] == 20
    assert top["similarity"] > 0.99


def test_find_similar_by_bounds_out_of_range_returns_empty(tmp_path):
    _noise(tmp_path / "shot.png", size=(50, 50), seed=7)
    # Bounds start past the image edge -> empty template -> [].
    assert VisualDetector().find_similar_by_bounds(tmp_path / "shot.png", (200, 200, 20, 20)) == []


def test_find_similar_by_bounds_missing_file_returns_empty(tmp_path):
    assert VisualDetector().find_similar_by_bounds(tmp_path / "nope.png", (0, 0, 10, 10)) == []


# --------------------------------------------------------------------------- #
# extract_element_screenshot
# --------------------------------------------------------------------------- #
def test_extract_element_screenshot_crops_region(tmp_path):
    from PIL import Image

    _solid(tmp_path / "shot.png", 90, size=(100, 100))
    out = tmp_path / "out" / "elem.png"
    VisualDetector().extract_element_screenshot(tmp_path / "shot.png", (10, 20, 30, 40), out)
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (30, 40)  # (width, height)


# --------------------------------------------------------------------------- #
# OCR: extract_text_from_image
# --------------------------------------------------------------------------- #
def test_init_sets_tesseract_cmd_when_path_given(monkeypatch):
    monkeypatch.setattr(vd, "TESSERACT_AVAILABLE", True)
    VisualDetector(tesseract_path="/usr/local/bin/tesseract")
    assert vd.pytesseract.pytesseract.tesseract_cmd == "/usr/local/bin/tesseract"


def test_extract_text_raises_when_tesseract_unavailable(tmp_path, monkeypatch):
    _solid(tmp_path / "shot.png", 255)
    monkeypatch.setattr(vd, "TESSERACT_AVAILABLE", False)
    with pytest.raises(RuntimeError):
        VisualDetector().extract_text_from_image(tmp_path / "shot.png")


def test_extract_text_returns_stripped_ocr_output(tmp_path, monkeypatch):
    _solid(tmp_path / "shot.png", 255, size=(80, 30))
    monkeypatch.setattr(vd, "TESSERACT_AVAILABLE", True)
    monkeypatch.setattr(vd.pytesseract, "image_to_string", lambda image: "  Hello World \n")
    text = VisualDetector().extract_text_from_image(tmp_path / "shot.png")
    assert text == "Hello World"


def test_extract_text_crops_to_region_before_ocr(tmp_path, monkeypatch):
    _solid(tmp_path / "shot.png", 255, size=(100, 100))
    seen = {}

    def fake_ocr(image):
        seen["size"] = image.size  # (width, height) of what OCR actually received
        return "x"

    monkeypatch.setattr(vd, "TESSERACT_AVAILABLE", True)
    monkeypatch.setattr(vd.pytesseract, "image_to_string", fake_ocr)
    VisualDetector().extract_text_from_image(tmp_path / "shot.png", region=(0, 0, 25, 35))
    assert seen["size"] == (25, 35)
