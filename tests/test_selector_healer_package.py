"""selector_healer.py was decomposed into a package (shared types + a stateless
strategy catalog + a FallbackTracker base + the SelectorHealer orchestrator).
These pin the split: the historical import path still works, the stateless
strategies behave, the healer inherits the fallback behaviour, and the two
responsibilities keep their own state.
"""

from framework.model.app_model import Selector

# Historical import path must keep working (re-exported from the package).
from framework.ml.selector_healer import HealingResult, HealingStrategy, SelectorHealer
from framework.ml.fallback_tracker import FallbackTracker
from framework.ml.healing_strategies import (
    heal_with_attributes,
    heal_with_hierarchy,
    heal_with_position,
    heal_with_text,
)


def _sel():
    return Selector(android="id/gone")


def test_selector_healer_is_a_fallback_tracker_with_partitioned_state():
    h = SelectorHealer()
    assert isinstance(h, FallbackTracker)
    # healing state
    assert h.healing_history == []
    assert h.healing_stats["visual_based"] == {"successes": 0, "failures": 0}
    # fallback state (inherited)
    assert h.fallback_reports == []
    assert h.page_object_updates == []


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


def test_heal_selector_prioritizes_text_and_records_history():
    h = SelectorHealer()
    result = h.heal_selector(_sel(), {"text": "Submit", "platform": "android"})
    assert result.success
    assert result.strategy == HealingStrategy.TEXT_BASED
    assert len(h.healing_history) == 1
    stats = h.get_healing_stats()
    assert stats["total_attempts"] == 1 and stats["successful"] == 1


def test_heal_selector_reports_failure_when_no_context():
    h = SelectorHealer()
    result = h.heal_selector(_sel(), {})
    assert not result.success
    assert result.reason == "All healing strategies failed"
    assert len(h.healing_history) == 1


def test_fallback_reporting_and_stats():
    h = SelectorHealer()
    h.report_fallback_usage(
        element_name="login_button",
        page_object_file="nonexistent_login_page.py",
        primary_selector="id/login",
        successful_fallback="//*[@text='Login']",
        fallback_index=0,
        platform="android",
    )
    stats = h.get_fallback_stats()
    assert stats["total_fallbacks"] == 1
    assert stats["unique_elements"] == 1
    assert stats["by_platform"]["android"] == 1


def test_auto_update_promotes_a_repeated_fallback_to_primary(tmp_path):
    page = tmp_path / "login_page.py"
    page.write_text(
        'LOGIN_BUTTON_SELECTOR = {\n    "android": "id/old_login",\n    "ios": "name/Login"\n}\n',
        encoding="utf-8",
    )
    h = SelectorHealer()
    # 3+ reports of the same successful fallback trip the auto-update threshold.
    for _ in range(3):
        h.report_fallback_usage(
            element_name="login_button",
            page_object_file=str(page),
            primary_selector="id/old_login",
            successful_fallback="id/new_login",
            fallback_index=0,
            platform="android",
        )
    assert "id/new_login" in page.read_text()  # promoted to primary
    assert (tmp_path / "login_page.py.bak").exists()  # original backed up
    assert h.page_object_updates  # recorded
