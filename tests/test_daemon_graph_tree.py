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


# --- session-driven UI tree: works on both Android and iOS ---------------------


class _FakeDriver:
    """A stand-in crawler driver: serves a canned page source, records quit()."""

    def __init__(self, source):
        self._source = source
        self.quit_called = False

    def page_source(self):
        return self._source

    def quit(self):
        self.quit_called = True


def test_ui_tree_uses_the_session_driver_regardless_of_platform():
    server = JSONRPCServer()
    # An iOS session with a pre-built driver — no real device needed.
    server.sessions["s1"] = {"platform": "ios", "_driver": _FakeDriver(_SCREEN_XML)}
    tree = server.handle_get_ui_tree({"session_id": "s1"})
    assert tree["element_count"] >= 1
    assert any(e.get("resource_id") == "com.x:id/login" for e in tree["elements"])


def test_session_driver_builds_ios_driver_for_ios_platform(monkeypatch):
    built = {}

    class _StubIOS:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setattr("framework.crawler.appium_driver.IOSCrawlerDriver", _StubIOS)
    server = JSONRPCServer()
    session = {"platform": "ios", "device_id": "UDID-1", "bundle_id": "com.acme.app", "server": "http://h:4723"}
    driver = server._session_driver(session)
    assert isinstance(driver, _StubIOS)
    assert built["udid"] == "UDID-1" and built["bundle_id"] == "com.acme.app" and built["server"] == "http://h:4723"
    assert session["_driver"] is driver  # cached on the session


def test_session_driver_builds_adb_driver_for_android(monkeypatch):
    class _StubAdb:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("framework.crawler.adb_driver.AdbCrawlerDriver", _StubAdb)
    server = JSONRPCServer()
    driver = server._session_driver({"platform": "android", "device_id": "emulator-5554"})
    assert isinstance(driver, _StubAdb)
    assert driver.kwargs["serial"] == "emulator-5554"


def test_session_driver_is_cached_not_rebuilt():
    server = JSONRPCServer()
    fake = _FakeDriver(_SCREEN_XML)
    session = {"platform": "ios", "_driver": fake}
    assert server._session_driver(session) is fake  # returns the cached one, builds nothing


def test_session_start_stores_ios_connection_fields():
    server = JSONRPCServer()
    res = server.handle_session_start(
        {"device_id": "UDID-1", "platform": "ios", "bundle_id": "com.acme.app", "server": "http://h:4723"}
    )
    session = server.sessions[res["session_id"]]
    assert session["platform"] == "ios"
    assert session["bundle_id"] == "com.acme.app"
    assert session["server"] == "http://h:4723"


def test_session_stop_quits_the_driver():
    server = JSONRPCServer()
    fake = _FakeDriver(_SCREEN_XML)
    server.sessions["s2"] = {"platform": "ios", "_driver": fake}
    server.handle_session_stop({"session_id": "s2"})
    assert fake.quit_called
    assert "s2" not in server.sessions
