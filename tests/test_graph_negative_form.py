"""Codegen: negative-path form tests (`graph.negative_form_cases`).

The generated suite must cover both branches of a form. `multi_step_cases`
already fills forms with *valid* data; these pin the *negative* counterpart —
navigate to a form, type invalid data, submit, and assert it is rejected (the
form did not advance).
"""

import pytest

from framework.crawler import graph as G
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    # Force the heuristic classifier (no ML model), so tests are fast and stable.
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def _el(cls, text="", rid="", desc="", clk=True):
    return CrawlElement(
        resource_id=rid,
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=clk,
        bounds=(0, 0, 300, 60),
        package="com.x",
    )


def _btn(label, rid):
    return _el("android.widget.Button", text=label, rid=rid)


def _screen(fp, els):
    return CrawlScreen(fingerprint=fp, elements=els, platform="android", toolkit="native")


def _email_form_result():
    """Entry screen A → (tap Open) → form screen B (email input + Continue)."""
    form = _screen(
        "B",
        [
            _el("android.widget.EditText", rid="com.x:id/email", desc="Email"),
            _btn("Continue", "com.x:id/continue"),
        ],
    )
    res = CrawlResult(
        screens={
            "A": _screen("A", [_btn("Open", "com.x:id/open")]),
            "B": form,
        }
    )
    res.transitions = [("A", _btn("Open", "com.x:id/open"), "B")]
    return res


def test_generates_a_negative_case_for_a_form():
    cases = G.negative_form_cases(_email_form_result(), "com.x")
    assert len(cases) == 1
    case = cases[0]
    assert "rejects_invalid_input" in case.name


def test_negative_case_types_invalid_data_then_submits_and_asserts():
    case = G.negative_form_cases(_email_form_result(), "com.x")[0]
    actions = [s.action.value for s in case.steps]
    # launch -> navigate (tap Open) -> type invalid -> tap submit -> assert
    assert actions[0] == "launch"
    types = [s for s in case.steps if s.action.value == "type"]
    assert [s.text for s in types] == ["not-an-email"]  # the invalid email, not a valid one
    assert actions[-1] == "assert"
    # The final assertion checks the form did NOT advance (submit still visible).
    assert case.steps[-1].assertion.value == "visible"
    assert "did not advance" in case.steps[-1].description


def test_navigates_to_the_form_before_typing():
    case = G.negative_form_cases(_email_form_result(), "com.x")[0]
    taps = [s for s in case.steps if s.action.value == "tap"]
    # One nav tap (Open) to reach the form, then the submit tap.
    assert len(taps) == 2
    # The nav tap comes before the first type step.
    first_type = next(i for i, s in enumerate(case.steps) if s.action.value == "type")
    first_tap = next(i for i, s in enumerate(case.steps) if s.action.value == "tap")
    assert first_tap < first_type


def test_no_case_without_a_submit_control():
    # An input but no submit-like button -> not a submittable form.
    res = CrawlResult(
        screens={
            "A": _screen("A", [_btn("Open", "com.x:id/open")]),
            "B": _screen(
                "B", [_el("android.widget.EditText", rid="com.x:id/email", desc="Email"), _btn("Help", "id/h")]
            ),
        }
    )
    res.transitions = [("A", _btn("Open", "com.x:id/open"), "B")]
    assert G.negative_form_cases(res, "com.x") == []


def test_no_case_without_a_typed_field():
    # A submit button but only an untyped/generic input -> no invalid value to type.
    res = CrawlResult(
        screens={
            "A": _screen("A", [_btn("Open", "com.x:id/open")]),
            "B": _screen("B", [_el("android.widget.EditText", rid="com.x:id/note", desc="Note"), _btn("Save", "id/s")]),
        }
    )
    res.transitions = [("A", _btn("Open", "com.x:id/open"), "B")]
    # "note" matches no strongly-typed rule -> invalid value is "" -> skipped.
    assert G.negative_form_cases(res, "com.x") == []


def test_skips_unreachable_form():
    # Form screen C is not reachable from the entry -> no navigation, no case.
    res = CrawlResult(
        screens={
            "A": _screen("A", [_btn("Open", "com.x:id/open")]),
            "B": _screen("B", [_btn("Leaf", "id/leaf")]),
            "C": _screen(
                "C",
                [_el("android.widget.EditText", rid="com.x:id/email", desc="Email"), _btn("Continue", "id/cont")],
            ),
        }
    )
    res.transitions = [("A", _btn("Open", "com.x:id/open"), "B")]  # nothing reaches C
    assert G.negative_form_cases(res, "com.x") == []


def test_wired_into_build_test_model():
    from framework.crawler.to_codegen import build_test_model

    model = build_test_model(_email_form_result(), "com.x")
    assert any("rejects_invalid_input" in c.name for c in model.cases)


def test_submit_element_skips_financial_controls():
    # CS2: the codegen submit picker must never target a money-moving control, so a generated
    # negative/fuzz case can't tap "Transfer"/"Send"/"Confirm" when the user runs the kit.
    transfer = _btn("Transfer", "com.x:id/transfer")
    cont = _btn("Continue", "com.x:id/continue")
    # Only a financial submit present -> None (no case is built around it).
    assert G._submit_element(_screen("F", [transfer]), "com.x") is None
    # A safe submit alongside a financial one -> the safe one is chosen.
    picked = G._submit_element(_screen("F", [transfer, cont]), "com.x")
    assert picked is not None and picked.text == "Continue"
