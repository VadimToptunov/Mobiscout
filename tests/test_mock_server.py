"""Mock layer (device-free): recordings transform, emitted-file validity, an
in-process replay proving determinism, and the pipeline writing it from a HAR."""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

from framework.codegen.mock_server import build_recordings, emit_mock_server


def _call(method, url, status, body, headers=None):
    return SimpleNamespace(
        method=method, url=url, response_status=status, response_body=body, response_headers=headers or {}
    )


def test_build_recordings_one_per_route_prefers_non_5xx():
    calls = [
        _call("GET", "https://api.x.com/cards?page=1", 500, "err"),
        _call("GET", "https://api.x.com/cards?page=2", 200, '{"ok":true}'),
        _call("POST", "https://api.x.com/login", 201, '{"token":"t"}'),
    ]
    by = {(r["method"], r["path"]): r for r in build_recordings(calls)}
    assert set(by) == {("GET", "/cards"), ("POST", "/login")}  # keyed by method+path, query ignored
    assert by[("GET", "/cards")]["status"] == 200  # the 500 was replaced by the good response
    assert by[("GET", "/cards")]["body"] == '{"ok":true}'


def test_emit_files_valid_and_port_from_base_url():
    files = emit_mock_server([_call("GET", "http://h/ping", 200, "pong")], base_url="http://localhost:9100")
    assert set(files) == {"recordings.json", "mock_server.py", "README.md"}
    json.loads(files["recordings.json"])  # valid JSON
    compile(files["mock_server.py"], "mock_server.py", "exec")  # valid Python
    assert "9100" in files["mock_server.py"]  # default port taken from the base URL


def test_emit_empty_without_calls():
    assert emit_mock_server([]) == {}


def test_emitted_server_replays_deterministically(tmp_path):
    files = emit_mock_server([_call("GET", "http://h/cards", 200, '{"cards":[]}')], base_url="http://localhost:8000")
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    spec = importlib.util.spec_from_file_location("mock_srv", tmp_path / "mock_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._load(str(tmp_path / "recordings.json"))

    server = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/cards", timeout=5)
        assert resp.status == 200
        assert json.loads(resp.read()) == {"cards": []}
        # An unrecorded route is a clean 404, not a hang.
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=5)
            raise AssertionError("expected 404")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.shutdown()


def test_pipeline_emits_mock_from_har(tmp_path):
    from framework.crawler.pipeline import emit_mock_from_har

    har = {
        "log": {
            "entries": [
                {
                    "request": {"method": "GET", "url": "http://api/ping", "headers": []},
                    "response": {
                        "status": 200,
                        "headers": [{"name": "Content-Type", "value": "application/json"}],
                        "content": {"text": '{"ok":1}'},
                    },
                }
            ]
        }
    }
    (tmp_path / "cap.har").write_text(json.dumps(har), encoding="utf-8")
    count = emit_mock_from_har(str(tmp_path / "cap.har"), tmp_path / "kit")
    assert count == 1
    assert (tmp_path / "kit" / "mock" / "mock_server.py").exists()
    assert (tmp_path / "kit" / "mock" / "recordings.json").exists()


def test_no_har_is_noop(tmp_path):
    from framework.crawler.pipeline import emit_mock_from_har

    assert emit_mock_from_har(None, tmp_path / "kit") == 0
