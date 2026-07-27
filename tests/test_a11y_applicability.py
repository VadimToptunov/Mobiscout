"""The non-colour a11y checks (touch-target, content-description, text-size) are
tri-state: a check only counts when it actually APPLIES to an element. A
'not applicable' result — e.g. touch-target sizing on a non-clickable element, or
a content-description check on a static label — must be neither a pass nor a
violation. Previously each not-applicable result was counted as ``pass_count += 1``,
which inflated the compliance score (a screen of static text scored ~100%).
"""

from framework.analysis.accessibility_analyzer import AccessibilityScanner, WCAGLevel


def _scan(node):
    # No colours are supplied, so contrast is 'not checked' and never counted —
    # this isolates the touch/content-desc/text-size accounting under test.
    return AccessibilityScanner(wcag_level=WCAGLevel.AA).scan_hierarchy(node, "App", "Home")


# A clickable button that is too small AND has no description: both applicable
# checks fail (touch-target + content-description); it has no text, so text-size
# is not applicable.
_BAD_BUTTON = {"id": "btn", "clickable": True, "bounds": {"width": 10, "height": 10}}

# A fully-compliant clickable button: big enough, has a content description, no
# text (text-size N/A). Both applicable checks pass.
_GOOD_BUTTON = {
    "id": "ok",
    "clickable": True,
    "content_desc": "Save",
    "bounds": {"width": 100, "height": 100},
}

# A static label: not clickable, not interactive, text present but no known font
# size. All three checks are 'not applicable'.
_STATIC_LABEL = {"id": "lbl", "text": "Hello"}


def test_not_applicable_elements_contribute_no_checks():
    """A tree of purely-static elements yields zero counted checks (not a pile of
    free passes). compliance_score falls back to its empty-scan default."""
    tree = {"id": "root", "children": [dict(_STATIC_LABEL), dict(_STATIC_LABEL)]}
    result = _scan(tree)

    assert result.total_checks == 0
    assert result.pass_count == 0
    assert result.compliance_score == 0.0  # 0/0 guarded to 0.0


def test_compliance_score_reflects_only_applicable_checks():
    """One bad button: exactly its two applicable checks are counted, both fail."""
    tree = {"id": "root", "children": [dict(_BAD_BUTTON)]}
    result = _scan(tree)

    assert result.total_checks == 2  # touch-target + content-description
    assert result.pass_count == 0
    assert result.compliance_score == 0.0


def test_na_siblings_do_not_inflate_a_failing_score():
    """Padding the screen with not-applicable static labels must not raise the
    score of a failing button. Previously each label added 3 phantom passes."""
    bare = {"id": "root", "children": [dict(_BAD_BUTTON)]}
    padded = {"id": "root", "children": [dict(_BAD_BUTTON)] + [dict(_STATIC_LABEL) for _ in range(20)]}

    bare_result = _scan(bare)
    padded_result = _scan(padded)

    assert padded_result.total_checks == bare_result.total_checks == 2
    assert padded_result.compliance_score == bare_result.compliance_score == 0.0


def test_na_siblings_do_not_dilute_a_passing_score():
    """A screen with one fully-compliant button scores 100%, and static N/A
    siblings keep it at 100% (they add no checks)."""
    tree = {"id": "root", "children": [dict(_GOOD_BUTTON)] + [dict(_STATIC_LABEL) for _ in range(5)]}
    result = _scan(tree)

    assert result.total_checks == 2  # both from the button; labels are N/A
    assert result.pass_count == 2
    assert result.compliance_score == 100.0
