"""Daemon methods that give the plugin real data: flow/getGraph (interaction
graph), a real ui/getTree (parsed elements, not a mock), and codegen/generate."""

import pytest

from framework.cli.daemon_commands import JSONRPCServer, ui_tree


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("OBSERVE_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("OBSERVE_ML_MODEL", "/nonexistent.pkl")


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
