"""The selector-healing helpers — the stateless strategy catalog, the
FallbackTracker, and the shared HealingResult — were relocated from
framework.ml into the framework.healing package (their proper home). The former
SelectorHealer orchestrator was dropped as a duplicate of HealingOrchestrator.
These pin that the helpers work from their new home.
"""

from framework.model.app_model import Selector
from framework.healing import (
    FallbackTracker,
    HealingResult,
    heal_with_attributes,
    heal_with_hierarchy,
    heal_with_position,
    heal_with_text,
)


def _sel():
    return Selector(android="id/gone")


def test_stateless_strategies_build_selectors_from_context():
    assert heal_with_text(_sel(), {"text": "Login", "platform": "android"}).healed_selector == (
        "//android.widget.*[@text='Login']"
    )
    assert heal_with_attributes(_sel(), {"content_desc": "Login", "platform": "android"}).success
    assert heal_with_hierarchy(_sel(), {"parent": {"class": "FrameLayout"}, "text": "Go"}).success
    assert heal_with_position(_sel(), {"position": 2, "class": "android.widget.Button"}).success


def test_stateless_strategies_fail_cleanly_without_context():
    for fn in (heal_with_text, heal_with_attributes, heal_with_hierarchy, heal_with_position):
        result = fn(_sel(), {})
        assert isinstance(result, HealingResult)
        assert not result.success
        assert result.healed_selector is None


def test_fallback_reporting_and_stats():
    t = FallbackTracker()
    t.report_fallback_usage(
        element_name="login_button",
        page_object_file="nonexistent_login_page.py",
        primary_selector="id/login",
        successful_fallback="//*[@text='Login']",
        fallback_index=0,
        platform="android",
    )
    stats = t.get_fallback_stats()
    assert stats["total_fallbacks"] == 1
    assert stats["unique_elements"] == 1
    assert stats["by_platform"]["android"] == 1


def test_auto_update_promotes_a_repeated_fallback_to_primary(tmp_path):
    page = tmp_path / "login_page.py"
    page.write_text(
        'LOGIN_BUTTON_SELECTOR = {\n    "android": "id/old_login",\n    "ios": "name/Login"\n}\n',
        encoding="utf-8",
    )
    t = FallbackTracker()
    # 3+ reports of the same successful fallback trip the auto-update threshold.
    for _ in range(3):
        t.report_fallback_usage(
            element_name="login_button",
            page_object_file=str(page),
            primary_selector="id/old_login",
            successful_fallback="id/new_login",
            fallback_index=0,
            platform="android",
        )
    assert "id/new_login" in page.read_text(encoding="utf-8")  # promoted to primary
    assert (tmp_path / "login_page.py.bak").exists()  # original backed up
    assert t.page_object_updates  # recorded
