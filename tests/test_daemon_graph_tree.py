"""Daemon methods that give the plugin real data: flow/getGraph (interaction
graph), a real ui/getTree (parsed elements, not a mock), and codegen/generate."""

import pytest

from framework.cli.daemon_commands import JSONRPCServer, generate_selector, ui_tree

_SCREEN_XML = (
    '<hierarchy><node class="android.widget.FrameLayout" resource-id="" text="" content-desc="" '
    'clickable="false" bounds="[0,0][200,400]" package="com.x">'
    '<node class="android.widget.Button" resource-id="com.x:id/login" text="Sign in" content-desc="" '
    'clickable="true" bounds="[20,100][180,160]" package="com.x"/></node></hierarchy>'
)


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def test_crawl_graph_returns_graph_dict():
    from framework.crawler.pipeline import crawl_graph
    from tests.test_crawler import APP, FakeDriver

    graph = crawl_graph({"package": APP}, driver=FakeDriver())
    assert "nodes" in graph and "edges" in graph and "metrics" in graph
    assert graph["metrics"]["screens"] >= 1


def test_ui_tree_parses_real_elements_not_mock():
    xml = (
        '<hierarchy><node class="android.widget.Button" resource-id="com.x:id/login" '
        'text="Sign in" content-desc="" clickable="true" bounds="[0,0][100,50]" package="com.x"/>'
        '<node class="android.widget.EditText" resource-id="com.x:id/email" text="" '
        'content-desc="Email" clickable="true" bounds="[0,60][100,110]" package="com.x"/></hierarchy>'
    )
    tree = ui_tree(xml)
    assert tree["platform"] == "android"
    assert tree["element_count"] == 2
    types = {e["type"] for e in tree["elements"]}
    assert "button" in types and "input" in types
    assert any(e["resource_id"] == "com.x:id/login" for e in tree["elements"])


def test_daemon_registers_new_methods():
    srv = JSONRPCServer()
    for m in ("flow/getGraph", "codegen/generate", "ui/getTree", "environment/detect"):
        assert m in srv.handlers


def test_flow_get_graph_requires_package():
    with pytest.raises(ValueError):
        JSONRPCServer().handle_flow_get_graph({})


def test_codegen_generate_is_kit_generate_alias():
    srv = JSONRPCServer()
    assert srv.handlers["codegen/generate"] == srv.handlers["kit/generate"]


def test_ui_tree_on_unknown_session_raises():
    with pytest.raises(ValueError):
        JSONRPCServer().handle_get_ui_tree({"session_id": "nope"})


def test_selector_generate_from_source_and_point():
    # A tap inside the button resolves to the button's ranked locator, not the frame.
    result = generate_selector({"source": _SCREEN_XML, "x": 100, "y": 130})
    assert result["found"] is True
    assert result["type"] == "button"
    assert result["selector"]["value"] == "com.x:id/login"


def test_selector_generate_from_element_attributes():
    result = generate_selector(
        {
            "element": {
                "resource_id": "",
                "content_desc": "Search",
                "class": "android.widget.ImageButton",
                "clickable": True,
                "bounds": [0, 0, 50, 50],
            }
        }
    )
    assert result["found"] is True
    assert result["selector"]["strategy"] == "accessibility_id"
    assert result["selector"]["value"] == "Search"


def test_selector_generate_point_off_target_not_found():
    result = generate_selector({"source": _SCREEN_XML, "x": 5, "y": 5})  # only the label-less frame
    assert result["found"] is False and result["selector"] is None


def test_selector_generate_requires_valid_params():
    with pytest.raises(ValueError):
        generate_selector({})


def test_selector_generate_registered_and_routed():
    srv = JSONRPCServer()
    assert "selector/generate" in srv.handlers
    resp = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "selector/generate",
            "params": {"source": _SCREEN_XML, "x": 100, "y": 130},
        }
    )
    assert resp["result"]["selector"]["value"] == "com.x:id/login"
