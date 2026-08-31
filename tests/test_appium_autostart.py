"""Auto-start Appium on a free port when a crawl needs it and none is running, so the
user doesn't have to install-and-start Appium by hand before every session. These pin
ensure_appium's decision table without a real Appium install (via its injectable seams)."""

import socket

import pytest

from framework.crawler import appium_server
from framework.crawler.appium_server import (
    _free_port,
    _is_default_local,
    ensure_appium,
    find_appium_executable,
)
from framework.crawler.errors import CrawlerDriverError


class _FakeManaged:
    """Stands in for a launched Appium server: start() is a no-op that yields a URL."""

    def __init__(self, executable, host="127.0.0.1"):
        self.executable = executable
        self.url = "http://127.0.0.1:55555"
        self.started = False
        self.stopped = False

    def start(self, ready_timeout=40.0):
        self.started = True
        return self

    def stop(self):
        self.stopped = True


def _reachable(_server):
    return True, "3.6.0"


def _unreachable(_server):
    return False, None


def test_reuses_a_reachable_server_without_starting_one():
    started = []
    url, managed = ensure_appium(
        "http://localhost:4723",
        status=_reachable,
        finder=lambda: (_ for _ in ()).throw(AssertionError("finder must not run when reachable")),
        server_factory=lambda exe: started.append(exe) or _FakeManaged(exe),
    )
    assert url == "http://localhost:4723"
    assert managed is None
    assert started == [], "must not auto-start when a server is already reachable"


def test_auto_starts_on_the_default_local_address_when_none_is_running():
    made = _FakeManaged("/usr/bin/appium")
    url, managed = ensure_appium(
        None,  # unset -> default local
        status=_unreachable,
        finder=lambda: "/usr/bin/appium",
        server_factory=lambda exe: made,
    )
    assert managed is made and made.started
    assert url == made.url, "the crawl must use the auto-started server's URL"


def test_does_not_auto_start_for_an_explicit_remote_hub():
    # A cloud-grid URL that's down is a real error — never silently spin up a local server.
    with pytest.raises(CrawlerDriverError):
        ensure_appium(
            "http://grid.example.com:4444/wd/hub",
            status=_unreachable,
            finder=lambda: "/usr/bin/appium",
            server_factory=lambda exe: pytest.fail("must not auto-start for a remote hub"),
        )


def test_actionable_error_when_appium_is_not_installed():
    with pytest.raises(CrawlerDriverError) as exc:
        ensure_appium(
            "http://localhost:4723",
            status=_unreachable,
            finder=lambda: None,  # not installed
            server_factory=lambda exe: pytest.fail("nothing to start"),
        )
    assert "npm install -g appium" in str(exc.value)


@pytest.mark.parametrize(
    "server,expected",
    [
        (None, True),
        ("", True),
        ("http://localhost:4723", True),
        ("http://127.0.0.1:4723", True),
        ("http://localhost:4723/", True),
        ("http://grid.example.com:4444", False),
        ("http://192.168.1.10:4723", False),
    ],
)
def test_is_default_local(server, expected):
    assert _is_default_local(server) is expected


def test_free_port_is_actually_bindable():
    port = _free_port()
    assert 1024 < port < 65536
    # If it's really free we can bind it right now.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_find_appium_prefers_path(monkeypatch):
    monkeypatch.setattr(appium_server.shutil, "which", lambda name: "/somewhere/bin/appium")
    assert find_appium_executable() == "/somewhere/bin/appium"


def test_find_appium_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(appium_server.shutil, "which", lambda name: None)
    # No candidate paths exist in the test environment.
    monkeypatch.setattr(appium_server.os.path, "isfile", lambda p: False)
    assert find_appium_executable() is None
