"""A per-screen state check for a NON-entry screen must navigate there first,
or it asserts a deeper screen's controls right after a bare launch and fails on a
real device (found running the generated iOS suite live). This pins that
build_test_model prefixes such state cases with the navigation taps, and skips
unreachable screens (which can't be state-tested at all).
"""

from framework.codegen.ir import ActionType
from framework.crawler.models import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import build_test_model


def _el(text, rid="", clickable=True):
    return CrawlElement(
        resource_id=rid,
        text=text,
        content_desc="",
        class_name="android.widget.Button",
        clickable=clickable,
        bounds=(0, 0, 10, 10),
    )


def _screen(fp, *els):
    return CrawlScreen(fingerprint=fp, elements=list(els))


def _case(model, name_contains):
    return next((c for c in model.cases if name_contains in c.name), None)


def test_non_entry_state_case_navigates_before_asserting():
    home = _screen("home", _el("Login", "id/login"))
    settings = _screen("settings", _el("Profile", "id/profile"), _el("Log out", "id/logout"))
    result = CrawlResult(
        screens={"home": home, "settings": settings},
        transitions=[("home", _el("Login", "id/login"), "settings")],
    )
    model = build_test_model(result, "com.example.app")

    # The entry screen's state case launches and asserts, with no navigation tap.
    entry = _case(model, "screen_1")
    assert entry is not None
    assert not any(s.action == ActionType.TAP for s in entry.steps)

    # A non-entry screen's state case taps its way there before any assertion.
    deeper = _case(model, "screen_2")
    assert deeper is not None
    first_assert = next(i for i, s in enumerate(deeper.steps) if s.action == ActionType.ASSERT)
    assert any(s.action == ActionType.TAP for s in deeper.steps[:first_assert])


def test_unreachable_screen_gets_no_state_case():
    home = _screen("home", _el("Login", "id/login"))
    orphan = _screen("orphan", _el("Ghost", "id/ghost"))  # no transition reaches it
    result = CrawlResult(screens={"home": home, "orphan": orphan}, transitions=[])
    model = build_test_model(result, "com.example.app")
    # Only the entry screen is state-testable; the orphan is skipped.
    assert _case(model, "screen_2") is None
