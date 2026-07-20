"""State checks should be meaningful, not exhaustive: assert a screen's landmark
and its actionable elements, not every decorative label / price."""

import pytest

from framework.codegen.ir import ActionType
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import build_test_model


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def _el(cls, text="", rid="", desc="", clk=True):
    return CrawlElement(
        resource_id=(f"com.x:id/{rid}" if rid else ""),
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=clk,
        bounds=(0, 0, 300, 60),
        package="com.x",
    )


def test_state_case_keeps_actionable_drops_decoration():
    screen = CrawlScreen(
        "product",
        [
            _el("android.widget.TextView", "Running Shoes", clk=False),  # landmark (kept)
            _el("android.widget.TextView", "$89.00", clk=False),  # decoration (dropped)
            _el("android.widget.TextView", "In stock", clk=False),  # decoration (dropped)
            _el("android.widget.EditText", rid="qty", desc="Quantity"),  # actionable (kept)
            _el("android.widget.Button", "Add to cart", rid="add"),  # actionable (kept)
        ],
        platform="android",
    )
    model = build_test_model(CrawlResult(screens={"product": screen}), app_package="com.x")
    state = next(c for c in model.cases if c.name.endswith("_shows_expected_controls"))
    asserted = {s.description for s in state.steps if s.action is ActionType.ASSERT}
    joined = " ".join(asserted)

    assert "Add to cart is visible" in joined and "Quantity is visible" in joined
    assert "Running Shoes is visible" in joined  # one landmark for identity
    assert "$89.00" not in joined and "In stock" not in joined  # decoration left to the inventory


def test_navigation_asserts_a_landmark_distinctive_to_the_destination():
    """A navigate_ case must assert an element unique to the destination — not
    shared chrome (a tab bar) that's on the start screen too, which would pass even
    if navigation silently failed."""
    shared = _el("android.widget.Button", desc="tab_home")  # chrome on both screens
    trigger = _el("android.widget.Button", "Go", rid="go")  # the nav trigger on start
    unique = _el("android.widget.TextView", "Markets", desc="markets_title", clk=False)  # only on dest
    start = CrawlScreen("start", [shared, trigger], platform="android")
    dest = CrawlScreen("dest", [shared, unique], platform="android")
    result = CrawlResult(
        screens={"start": start, "dest": dest},
        transitions=[("start", trigger, "dest")],
    )
    model = build_test_model(result, app_package="com.x")
    nav = next(c for c in model.cases if c.name.startswith("tapping_"))
    landmark = next(s for s in nav.steps if s.action is ActionType.ASSERT)
    assert landmark.selector.value == "markets_title"  # distinctive, not the shared "tab_home"


def test_many_actionable_elements_are_capped():
    els = [_el("android.widget.Button", f"Item {i}", rid=f"i{i}") for i in range(20)]
    screen = CrawlScreen("list", els, platform="android")
    model = build_test_model(CrawlResult(screens={"list": screen}), app_package="com.x")
    state = next(c for c in model.cases if c.name.endswith("_shows_expected_controls"))
    visible = [s for s in state.steps if s.action is ActionType.ASSERT and "is visible" in s.description]
    assert len(visible) <= 8  # capped, not one line per button
