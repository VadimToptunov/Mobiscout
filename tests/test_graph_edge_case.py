"""The interaction graph flags special screens (error / loading / permission /
network) from their element texts — edge-case detection harvested from the former
flow.flow_discovery into the live crawler.graph. Ordinary screens stay unflagged.
"""

from framework.crawler.graph import _classify_screen, build_graph
from framework.crawler.models import CrawlElement, CrawlResult, CrawlScreen


def _el(text: str) -> CrawlElement:
    return CrawlElement(
        resource_id="",
        text=text,
        content_desc="",
        class_name="android.widget.TextView",
        clickable=True,
        bounds=(0, 0, 10, 10),
    )


def _screen(fp: str, *texts: str) -> CrawlScreen:
    return CrawlScreen(fingerprint=fp, elements=[_el(t) for t in texts])


def test_classify_screen_flags_and_ignores():
    assert _classify_screen(_screen("a", "Something went wrong", "Retry")) == "error_screen"
    assert _classify_screen(_screen("b", "Loading, please wait")) == "loading_screen"
    assert _classify_screen(_screen("c", "Allow  location permission?")) == "permission_dialog"
    assert _classify_screen(_screen("d", "No connection")) == "network_error"
    assert _classify_screen(_screen("e", "Login", "Sign up")) is None


def test_build_graph_sets_edge_case_on_nodes():
    home = _screen("home", "Login", "Sign up")
    error = _screen("err", "Error: something went wrong")
    result = CrawlResult(
        screens={"home": home, "err": error},
        transitions=[("home", _el("Login"), "err")],
    )
    graph = build_graph(result)
    by_fp = {n.fingerprint: n for n in graph.nodes}
    assert by_fp["err"].edge_case == "error_screen"
    assert by_fp["home"].edge_case is None
    # It is serialized for the report / JSON export.
    assert by_fp["err"].to_dict()["edge_case"] == "error_screen"
