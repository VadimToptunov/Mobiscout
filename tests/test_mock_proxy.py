"""The record/replay HTTP proxy must forward+capture live traffic in record mode
and serve it back with no upstream call in replay mode — the real behaviour behind
``observe mock record`` / ``observe mock replay``."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from framework.mocking import APIMocker, MockProxy


class _Upstream(BaseHTTPRequestHandler):
    """A tiny real backend: echoes a JSON body and counts how often it is hit."""

    hits = 0

    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        type(self).hits += 1
        payload = json.dumps({"path": self.path, "ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def upstream():
    _Upstream.hits = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _proxies(proxy: MockProxy) -> dict:
    host, port = proxy.address
    return {"http": f"http://{host}:{port}"}


def test_record_forwards_and_captures(tmp_path, upstream):
    up_host, up_port = upstream.server_address
    target = f"http://{up_host}:{up_port}/api/users"

    mocker = APIMocker(storage_dir=tmp_path)
    mocker.start_recording("sess")
    with MockProxy(mocker, port=0) as proxy:
        resp = requests.get(target, proxies=_proxies(proxy), timeout=5)

    # The real response is passed through untouched...
    assert resp.status_code == 200
    assert resp.json()["path"] == "/api/users"
    assert _Upstream.hits == 1
    # ...and the round-trip was recorded.
    stats = mocker.stop()
    assert stats["total_requests"] == 1
    assert mocker.storage.load_session("sess")[0].request.url == target


def test_replay_serves_without_hitting_upstream(tmp_path, upstream):
    up_host, up_port = upstream.server_address
    target = f"http://{up_host}:{up_port}/api/users"

    # First record one call.
    rec = APIMocker(storage_dir=tmp_path)
    rec.start_recording("sess")
    with MockProxy(rec, port=0) as proxy:
        requests.get(target, proxies=_proxies(proxy), timeout=5)
    rec.stop()
    hits_after_record = _Upstream.hits

    # Now replay: the upstream must NOT be hit again, body served from the mock.
    rep = APIMocker(storage_dir=tmp_path)
    rep.start_replay("sess")
    with MockProxy(rep, port=0) as proxy:
        resp = requests.get(target, proxies=_proxies(proxy), timeout=5)

    assert resp.status_code == 200
    assert resp.json()["path"] == "/api/users"
    assert _Upstream.hits == hits_after_record  # no new upstream call
    stats = rep.stop()
    assert stats["cache_hits"] == 1


def test_replay_miss_returns_504(tmp_path, upstream):
    up_host, up_port = upstream.server_address
    # Record nothing for this URL, then replay a request the session never saw.
    empty = APIMocker(storage_dir=tmp_path)
    empty.start_recording("sess")
    with MockProxy(empty, port=0) as proxy:
        requests.get(f"http://{up_host}:{up_port}/known", proxies=_proxies(proxy), timeout=5)
    empty.stop()

    rep = APIMocker(storage_dir=tmp_path)
    rep.start_replay("sess")
    with MockProxy(rep, port=0) as proxy:
        resp = requests.get(f"http://{up_host}:{up_port}/never-recorded", proxies=_proxies(proxy), timeout=5)

    assert resp.status_code == 504
    assert "no recorded mock" in resp.text
