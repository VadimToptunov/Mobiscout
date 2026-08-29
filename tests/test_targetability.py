"""Targetability: of the interactive elements a crawl found, how many carry an identity
that is not their visible caption.

Measured on real apps, Compose UIs land around 6-27% here while View/XML ones sit at
90-99% — findViewById forced an `android:id`, Compose forces nothing. The number is the
one a QA lead can act on, so the crawl reports it next to coverage.
"""

from framework.codegen.ir import TestModel
from framework.crawler.coverage_report import build_coverage
from framework.crawler.graph import InteractionGraph
from framework.crawler.models import CrawlElement, CrawlResult, CrawlScreen


def _element(resource_id: str = "", content_desc: str = "", text: str = "") -> CrawlElement:
    """One clickable control with whichever identity strings the case needs."""
    return CrawlElement(
        resource_id=resource_id,
        text=text,
        content_desc=content_desc,
        class_name="android.view.View",
        clickable=True,
        bounds=(0, 0, 100, 40),
    )


def _report(*elements: CrawlElement):
    """Build a coverage report over a single screen holding ``elements``."""
    result = CrawlResult(screens={"fp": CrawlScreen("fp", list(elements))})
    return build_coverage(result, InteractionGraph(), TestModel(name="probe", app_package="com.app"))


def test_a_resource_id_makes_an_element_targetable():
    report = _report(_element(resource_id="com.app:id/submit"))
    assert report.elements_targetable == 1 and report.targetability_pct() == 100


def test_an_accessibility_label_makes_an_element_targetable():
    report = _report(_element(content_desc="Close"))
    assert report.elements_targetable == 1


def test_visible_text_alone_does_not_count():
    # The whole point of the metric: a caption is content and moves with copy changes.
    report = _report(_element(text="Log in"))
    assert report.elements_targetable == 0 and report.targetability_pct() == 0


def test_an_element_with_no_identity_at_all_does_not_count():
    assert _report(_element()).elements_targetable == 0


def test_the_percentage_mixes_targetable_and_caption_only_controls():
    report = _report(
        _element(resource_id="com.app:id/a"),
        _element(content_desc="B"),
        _element(text="C"),
        _element(text="D"),
    )
    assert report.elements_targetable == 2 and report.targetability_pct() == 50


def test_the_numbers_reach_the_json_artifact():
    payload = _report(_element(resource_id="com.app:id/a"), _element(text="B")).to_dict()
    assert payload["elements_targetable"] == 1 and payload["targetability_pct"] == 50
    assert payload["screens"][0]["targetable"] == 1


def test_the_markdown_reports_the_share():
    markdown = _report(_element(resource_id="com.app:id/a"), _element(text="B")).to_markdown("com.app")
    assert "Targetable elements: **1/2**" in markdown
    assert "| Targetable |" in markdown
