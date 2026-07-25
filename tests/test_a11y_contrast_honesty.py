"""Colour-contrast a11y checks used to DEFAULT to black-on-white when an element
carried no colours — so every element silently scored 21:1 and passed, and "not
checked" was counted as a pass. Now contrast is only checked with real colours
(carried on the element or sampled from a screenshot via Pillow); elements with no
colours are counted as `contrast_not_checked`, never a silent pass.
"""

from PIL import Image

from framework.analysis.accessibility_analyzer import AccessibilityScanner, WCAGLevel


def test_no_colours_is_not_checked_not_a_silent_pass():
    scanner = AccessibilityScanner(wcag_level=WCAGLevel.AA)
    node = {"id": "t", "text": "hi", "bounds": {"width": 100, "height": 40}}
    result = scanner.scan_hierarchy(node, "App", "Home")
    assert result.contrast_not_checked == 1
    assert all(v.rule_id != "color-contrast" for v in result.violations)


def test_low_contrast_from_explicit_colours_is_a_violation():
    scanner = AccessibilityScanner(wcag_level=WCAGLevel.AA)
    node = {
        "id": "t",
        "text": "hi",
        "text_color": (200, 200, 200),  # light grey on white — fails AA
        "background_color": (255, 255, 255),
        "bounds": {"width": 100, "height": 40},
    }
    result = scanner.scan_hierarchy(node, "App", "Home")
    assert result.contrast_not_checked == 0
    assert any(v.rule_id == "color-contrast" for v in result.violations)


def test_good_contrast_from_explicit_colours_passes():
    scanner = AccessibilityScanner(wcag_level=WCAGLevel.AA)
    node = {
        "id": "t",
        "text": "hi",
        "text_color": (0, 0, 0),  # black on white — passes
        "background_color": (255, 255, 255),
        "bounds": {"width": 100, "height": 40},
    }
    result = scanner.scan_hierarchy(node, "App", "Home")
    assert result.contrast_not_checked == 0
    assert all(v.rule_id != "color-contrast" for v in result.violations)


def test_real_contrast_sampled_from_screenshot(tmp_path):
    # A screenshot where the element region is light-grey text on white.
    shot = tmp_path / "screen.png"
    img = Image.new("RGB", (200, 200), (255, 255, 255))  # white
    for x in range(20, 45):
        for y in range(25, 40):
            img.putpixel((x, y), (200, 200, 200))  # grey "text" pixels within the element
    img.save(shot)

    node = {"id": "t", "text": "hi", "bounds": {"x": 10, "y": 10, "width": 80, "height": 40}}
    scanner = AccessibilityScanner(wcag_level=WCAGLevel.AA)
    result = scanner.scan_hierarchy(node, "App", "Home", screenshot=shot)

    assert result.contrast_not_checked == 0  # colours were sampled, not skipped
    assert any(v.rule_id == "color-contrast" for v in result.violations)  # grey-on-white fails AA
