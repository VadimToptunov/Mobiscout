"""Robust app launch over adb: resolve the launchable activity and start it
explicitly (monkey silently fails to foreground some apps), polling until the app
is actually resumed. A capricious device shouldn't need a manual pre-launch."""

import framework.crawler.adb_driver as adb
from framework.crawler.adb_driver import AdbCrawlerDriver


def _driver(monkeypatch, run_fn, pkg_seq):
    d = AdbCrawlerDriver()
    monkeypatch.setattr(d, "_run", run_fn)
    seq = iter(pkg_seq)
    monkeypatch.setattr(d, "current_package", lambda: next(seq, pkg_seq[-1]))
    monkeypatch.setattr(adb.time, "sleep", lambda s: None)  # no real waiting in tests
    return d


def test_launch_resolves_activity_and_starts_it(monkeypatch):
    calls = []

    def run(*args):
        calls.append(args)
        if "resolve-activity" in args:
            return "priority=0\ncom.x/com.x.SplashActivity\n"
        return ""

    d = _driver(monkeypatch, run, ["", "com.x"])  # not foreground, then foreground
    assert d.launch("com.x") is True
    started = [a for a in calls if "am" in a and "start" in a]
    assert started and "com.x/com.x.SplashActivity" in started[0]


def test_launch_falls_back_to_monkey_when_no_activity_resolves(monkeypatch):
    calls = []

    def run(*args):
        calls.append(args)
        return ""  # resolve-activity returns nothing usable

    d = _driver(monkeypatch, run, ["com.x"])  # already foreground after launch
    assert d.launch("com.x") is True
    assert any("monkey" in a for a in calls)


def test_launch_returns_false_if_app_never_foregrounds(monkeypatch):
    d = _driver(monkeypatch, lambda *a: "", ["", "", "", ""])  # never becomes com.x
    assert d.launch("com.x", tries=3) is False
