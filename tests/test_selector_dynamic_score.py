"""The live selector builder (crawler.to_codegen._selector_for) scores a
text-based locator lower when the text looks dynamic (a count, price, timestamp) —
dynamic-text detection harvested from the former selectors.selector_scorer. Order
is unchanged (text stays the last-resort tier); only the stability score differs.
"""

from framework.crawler.app_crawler import CrawlElement
from framework.crawler.to_codegen import _looks_dynamic, _selector_for
from framework.codegen.ir import SelectorStrategy


def _text_element(text: str) -> CrawlElement:
    return CrawlElement(
        resource_id="",
        text=text,
        content_desc="",
        class_name="android.widget.TextView",
        clickable=True,
        bounds=(0, 0, 10, 10),
    )


def test_looks_dynamic():
    assert _looks_dynamic("Balance: $1,234.56")
    assert _looks_dynamic("12:45")
    assert _looks_dynamic("42 items")
    assert _looks_dynamic("OK")  # very short
    assert not _looks_dynamic("Login")
    assert not _looks_dynamic("Create account")


def test_stable_text_scores_higher_than_dynamic_text():
    stable = _selector_for(_text_element("Login"))
    dynamic = _selector_for(_text_element("Total: $99"))
    assert stable is not None and dynamic is not None
    assert stable.strategy is SelectorStrategy.TEXT
    assert dynamic.strategy is SelectorStrategy.TEXT
    assert stable.score == 0.60
    assert dynamic.score == 0.42
    assert dynamic.score < stable.score


def test_dynamic_penalty_does_not_change_tier_order():
    # A resource-id still wins primary over dynamic text (order unchanged).
    el = CrawlElement(
        resource_id="id/total",
        text="Total: $99",
        content_desc="",
        class_name="android.widget.TextView",
        clickable=True,
        bounds=(0, 0, 10, 10),
    )
    sel = _selector_for(el)
    assert sel is not None
    assert sel.strategy is SelectorStrategy.ID  # resource-id remains primary
