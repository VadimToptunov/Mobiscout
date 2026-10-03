"""In-crawl network capture (#312): mitmdump runs for the crawl and writes a HAR, the device is
routed through it and ALWAYS un-routed afterwards, and a crawl alone then yields API tests —
no external proxy capture. Driven with a fake mitmdump (a real listening socket + a HAR written
on SIGINT, as mitmdump's hardump does) and a fake adb, so it runs in CI."""

import json
import socket
from contextlib import contextmanager

import pytest

import framework.crawler.pipeline as pipeline
from framework.crawler.network_capture import EMULATOR_HOST, NetworkCapture, NetworkCaptureError
from framework.crawler.pipeline import run_kit
from tests.test_crawler import APP, FakeDriver

_HAR = {
    "log": {
        "entries": [
            {"request": {"method": "GET", "url": "https://api.shop.com/products"}, "response": {"status": 200}},
            {"request": {"method": "POST", "url": "https://api.shop.com/orders"}, "response": {"status": 201}},
        ]
    }
}


class _FakeMitmdump:
    """Listens on the port it was given (so the capture sees it come up) and writes the HAR on
    SIGINT, as mitmdump's hardump does on shutdown."""

    def __init__(self, args):
        self.args = args
        self.port = int(args[args.index("--listen-port") + 1])
        self.har = args[args.index("--set") + 1].split("=", 1)[1]
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", self.port))
        self.sock.listen()
        self.returncode = None
        self.signals = []

    def poll(self):
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        with open(self.har, "w", encoding="utf-8") as f:
            json.dump(_HAR, f)
        self.sock.close()
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


def _capture(tmp_path, platform="android", serial="emulator-5554", which=lambda _: "/usr/bin/mitmdump"):
    runs, spawned = [], []

    def spawn(args, **_kw):
        spawned.append(_FakeMitmdump(args))
        return spawned[-1]

    capture = NetworkCapture(
        tmp_path / "network.har",
        platform=platform,
        serial=serial,
        run=lambda cmd, **_kw: runs.append(cmd),
        spawn=spawn,
        which=which,
    )
    return capture, runs, spawned


def test_the_emulator_is_routed_through_the_proxy_and_the_har_is_written(tmp_path):
    capture, runs, spawned = _capture(tmp_path)
    with capture:
        assert runs == [
            [
                "adb",
                "-s",
                "emulator-5554",
                "shell",
                "settings",
                "put",
                "global",
                "http_proxy",
                f"{EMULATOR_HOST}:{capture.port}",
            ]
        ]
    assert runs[-1][-1] == ":0", "the device's proxy must be reset after the crawl"
    assert spawned[0].signals, "mitmdump is stopped with SIGINT so it writes the HAR"
    assert capture.captured == str(tmp_path / "network.har")


def test_the_proxy_is_reset_even_when_the_crawl_fails(tmp_path):
    capture, runs, _ = _capture(tmp_path)
    with pytest.raises(RuntimeError):
        with capture:
            raise RuntimeError("device went away")
    assert runs[-1][-1] == ":0"


def test_ios_is_not_rerouted_behind_your_back_but_told_what_to_set(tmp_path):
    capture, runs, _ = _capture(tmp_path, platform="ios", serial=None)
    with capture:
        pass
    assert runs == [], "the Mac's proxy settings are never changed by the crawl"
    assert f"127.0.0.1:{capture.port}" in capture.instructions


def test_missing_mitmproxy_is_a_clear_error(tmp_path):
    capture, _, _ = _capture(tmp_path, which=lambda _: None)
    with pytest.raises(NetworkCaptureError, match="pip install mitmproxy"):
        with capture:
            pass


def test_a_crawl_with_capture_network_yields_api_tests_without_a_har(tmp_path, monkeypatch):
    @contextmanager
    def fake_capture(config):
        capture, _, _ = _capture(tmp_path / "out")
        if not config.get("capture_network"):
            yield None
            return
        with capture:
            yield capture

    monkeypatch.setattr(pipeline, "network_capture_for", fake_capture)
    summary = run_kit({"package": APP, "output": str(tmp_path / "out"), "capture_network": True}, driver=FakeDriver())
    assert summary["network_capture"]["har"] == str(tmp_path / "out" / "network.har")
    assert summary["api_tests"] == 2
    assert (tmp_path / "out" / "test_api.py").exists()
