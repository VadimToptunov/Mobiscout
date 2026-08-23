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


def test_titleless_screen_is_named_from_its_fingerprint_not_its_index():
    # Review #8: a titleless screen used to be named screen_{enumeration index}, so inserting a
    # screen renumbered every later one and churned diff-aware CHANGES.md. The name is now a
    # pure function of the screen's own fingerprint — so it can't shift when another screen is
    # inserted, because `index` no longer appears in it.
    weak = _el("0")  # fragile numeric, no title
    strong = CrawlElement(
        resource_id="",
        text="Freeze card",
        content_desc="card.freezeToggle",
        class_name="android.widget.Button",
        clickable=True,
        bounds=(0, 20, 10, 30),
    )
    model = build_test_model(
        CrawlResult(screens={"deadbeefcafe": _screen("deadbeefcafe", weak, strong)}, transitions=[]),
        "com.x",
    )
    entry = _case(model, "screen_deadbeef")  # first 8 of the fingerprint
    assert entry is not None
    assert "index" not in entry.name and "screen_1" not in entry.name


def test_non_entry_state_case_navigates_before_asserting():
    home = _screen("home", _el("Login", "id/login"))
    settings = _screen("settings", _el("Profile", "id/profile"), _el("Log out", "id/logout"))
    result = CrawlResult(
        screens={"home": home, "settings": settings},
        transitions=[("home", _el("Login", "id/login"), "settings")],
    )
    model = build_test_model(result, "com.example.app")

    # The entry screen's state case launches and asserts, with no navigation tap.
    # (Screens are named after their landmark/control, so the login-form entry is
    # "login_screen..." and the deeper one "profile_screen...".)
    entry = _case(model, "login_screen")
    assert entry is not None
    assert not any(s.action == ActionType.TAP for s in entry.steps)

    # A non-entry screen's state case taps its way there before any assertion.
    deeper = _case(model, "profile_screen")
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


def test_state_case_skips_fragile_numeric_text_assertions():
    """An element whose only locator is a bare numeric/short text (e.g. "0") is a
    fragile state check (found running the ChaosBank suite live) — the state case
    must not assert it. A properly-identified control (accessibility id) stays."""
    # A button located only by the text "0" (dynamic/short -> low score) plus a
    # button with a stable accessibility id.
    weak = CrawlElement(
        resource_id="",
        text="0",
        content_desc="",
        class_name="android.widget.Button",
        clickable=True,
        bounds=(0, 0, 10, 10),
    )
    strong = CrawlElement(
        resource_id="",
        text="Freeze card",
        content_desc="card.freezeToggle",
        class_name="android.widget.Button",
        clickable=True,
        bounds=(0, 20, 10, 30),
    )
    result = CrawlResult(screens={"home": _screen("home", weak, strong)}, transitions=[])
    model = build_test_model(result, "com.example.app")
    # A titleless screen is named from its fingerprint (stable across insertions), not its index.
    entry = _case(model, "screen_home")
    assert entry is not None
    asserted = " ".join(s.selector.value for s in entry.steps if s.selector)
    assert "card.freezeToggle" in asserted  # the stable control is checked
    assert '"0"' not in asserted and "text('0')" not in asserted  # the fragile "0" is not
