"""Typed transitions (models.Transition): a negative-data *probe* edge must never become
a positive journey or a graph edge, while still unpacking as the legacy (src, el, dst)
triple. Guards review finding P0.2/F2 (probes poisoning journeys)."""

from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.graph import build_graph
from framework.crawler.models import Transition
from framework.crawler.to_codegen import _navigation_cases


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


def _result_with_probe():
    signin = _el("android.widget.Button", "Sign in", rid="signin")
    login = CrawlScreen(
        "login",
        [_el("android.widget.EditText", rid="email", desc="Email"), signin],
        platform="android",
    )
    home = CrawlScreen("home", [_el("android.widget.TextView", "Catalog", clk=False)], platform="android")
    error = CrawlScreen("error", [_el("android.widget.TextView", "Invalid credentials", clk=False)], platform="android")
    res = CrawlResult(screens={"login": login, "home": home, "error": error})
    res.transitions = [
        Transition("login", signin, "home"),  # a real navigation
        Transition("login", signin, "error", kind="probe"),  # a negative-data probe
    ]
    return res, {"login": 1, "home": 2, "error": 3}


def test_transition_unpacks_as_legacy_triple():
    t = Transition("a", _el("x"), "b", kind="probe")
    src, el, dst = t  # __iter__
    assert (src, dst) == ("a", "b")
    assert t[0] == "a" and t[2] == "b"  # __getitem__


def test_probe_edge_is_not_a_graph_edge():
    res, idx = _result_with_probe()
    graph = build_graph(res, "com.x")
    error_node = idx["error"]
    assert all(e.dst != error_node for e in graph.edges), "probe transition leaked into the graph"
    # the real login->home edge is still present
    assert any(e.src == idx["login"] and e.dst == idx["home"] for e in graph.edges)


def test_probe_edge_produces_no_navigation_case():
    res, _ = _result_with_probe()
    cases = _navigation_cases(res, "com.x")
    # No emitted case should assert the error screen's landmark.
    joined = " ".join(step.description or "" for c in cases for step in c.steps)
    assert "Invalid credentials" not in joined


def _gated_result():
    signin = _el("android.widget.Button", "Sign in", rid="signin")
    login = CrawlScreen(
        "login",
        [_el("android.widget.EditText", rid="user", desc="Username"), signin],
        platform="android",
    )
    home = CrawlScreen("home", [_el("android.widget.TextView", "Dashboard", clk=False)], platform="android")
    res = CrawlResult(screens={"login": login, "home": home})
    res.transitions = [Transition("login", signin, "home", kind="gate")]  # synthetic auth crossing
    res.gated = {"home"}
    res.auth_sequence = [
        {"action": "fill", "data": {"fields": {"username": "u", "password": "p"}, "submit": "Sign in"}}
    ]
    return res


def test_gate_edge_is_not_a_navigation_case():
    # The synthetic "tap Sign in -> home" gate edge must not become a positive nav
    # (that test would tap submit without filling the form and never reach home).
    assert _navigation_cases(_gated_result(), "com.x") == []


def test_gated_screen_case_carries_the_auth_prefix():
    from framework.crawler.to_codegen import build_test_model

    model = build_test_model(_gated_result(), app_package="com.x")
    descriptions = [s.description or "" for c in model.cases for s in c.steps]
    # The gated home screen is still covered — with the auth steps prepended so the
    # test actually gets there (login form filled), not a bare launch-and-assert.
    assert any("Enter username" in d for d in descriptions), "gated screen lost its auth prefix"
