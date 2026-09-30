"""The protocol-level fake Appium server the JVM/.NET kits execute against: it must behave like
the app model says — elements per screen, taps that navigate, app state, a crash, a dead
session — and fail loudly on anything it does not implement."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))
from fake_appium_server import ELEMENT_KEY, FakeAppiumServer  # noqa: E402

MODEL = {
    "start": 0,
    "screens": [[["id", "go"], ["id", "boom"], ["id", "kill"]], [["id", "arrived"]]],
    "transitions": [[0, "id", "go", 1]],
    "crashes": [[0, "id", "boom"]],
    "session_killers": [[0, "id", "kill"]],
}


def _call(server, method, path, body=None):
    data = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
    req = urllib.request.Request(server.url + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())["value"]
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())["value"]


def _session(server):
    return _call(server, "POST", "/session", {"capabilities": {}})[1]["sessionId"]


def _tap(server, sid, rid):
    _, ref = _call(server, "POST", f"/session/{sid}/element", {"using": "id", "value": rid})
    return _call(server, "POST", f"/session/{sid}/element/{ref[ELEMENT_KEY]}/click")


def test_a_tap_navigates_and_the_old_screen_is_gone():
    with FakeAppiumServer(MODEL) as server:
        sid = _session(server)
        _tap(server, sid, "go")
        assert _call(server, "POST", f"/session/{sid}/elements", {"using": "id", "value": "arrived"})[1]
        status, err = _call(server, "POST", f"/session/{sid}/element", {"using": "id", "value": "go"})
        assert status == 404 and err["error"] == "no such element"


@pytest.mark.parametrize("script", ["mobile: queryAppState", "mobile:queryAppState"])
def test_a_crash_shows_in_the_app_state_until_the_app_is_activated(script):
    with FakeAppiumServer(MODEL) as server:
        sid = _session(server)
        _tap(server, sid, "boom")
        assert _call(server, "POST", f"/session/{sid}/execute/sync", {"script": script, "args": []})[1] == 1
        _call(server, "POST", f"/session/{sid}/appium/device/activate_app", {"appId": "x"})
        assert _call(server, "POST", f"/session/{sid}/appium/device/app_state", {"appId": "x"})[1] == 4


def test_a_killed_session_answers_invalid_session_and_a_new_one_works():
    with FakeAppiumServer(MODEL) as server:
        sid = _session(server)
        _tap(server, sid, "kill")
        status, err = _call(server, "POST", f"/session/{sid}/elements", {"using": "id", "value": "go"})
        assert status == 404 and err["error"] == "invalid session id"
        fresh = _session(server)
        assert _call(server, "POST", f"/session/{fresh}/elements", {"using": "id", "value": "go"})[1]


def test_an_unknown_command_fails_loudly_and_is_recorded():
    with FakeAppiumServer(MODEL) as server:
        sid = _session(server)
        status, err = _call(server, "POST", f"/session/{sid}/appium/device/shake")
        assert status == 404 and err["error"] == "unknown command"
        assert server.unknown == ["POST /session/:id/appium/device/shake"]
