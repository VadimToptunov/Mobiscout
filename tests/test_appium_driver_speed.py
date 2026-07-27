"""The iOS driver pushes WDA onto its fast path (no idle wait, compact/bounded
snapshots) — the dominant iOS crawl-speed lever. Tested in isolation, no session."""

from framework.crawler.appium_driver import IOSCrawlerDriver


class _FakeDriver:
    def __init__(self):
        self.settings = None

    def update_settings(self, settings):
        self.settings = settings


def _driver_with(fake):
    # Build without going through __init__ (which would open a real Appium
    # session); we only exercise the speed-tuning method.
    d = IOSCrawlerDriver.__new__(IOSCrawlerDriver)
    d._driver = fake
    return d


def test_tune_for_speed_disables_idle_wait_and_bounds_snapshot():
    fake = _FakeDriver()
    _driver_with(fake)._tune_for_speed()
    assert fake.settings is not None
    # The key win: never wait for the app to be idle.
    assert fake.settings["waitForIdleTimeout"] == 0
    assert fake.settings["shouldUseCompactResponses"] is True
    assert fake.settings["snapshotMaxDepth"] > 0


def test_tune_for_speed_survives_a_server_that_rejects_settings():
    class _Rejecting:
        def update_settings(self, settings):
            raise RuntimeError("older server")

    # Must not raise — tuning is best-effort.
    _driver_with(_Rejecting())._tune_for_speed()


def _build_ios_driver(monkeypatch, process_args):
    """Construct IOSCrawlerDriver with a stubbed Appium session and return the
    capabilities it requested."""
    import appium.webdriver as awd

    captured = {}

    class _Session:
        def update_settings(self, settings):
            pass

    def fake_remote(server, options=None):
        captured["caps"] = options.to_capabilities()
        return _Session()

    monkeypatch.setattr(awd, "Remote", fake_remote)
    IOSCrawlerDriver("com.example.app", udid="U1", process_args=process_args)
    return captured["caps"]


def test_launch_args_force_a_fresh_relaunch(monkeypatch):
    # Regression: with launch args, the app MUST be relaunched or Appium attaches
    # to a running instance and silently drops the args (crawl stuck on the gate).
    caps = _build_ios_driver(monkeypatch, ["-ChaosBankStartUnlocked", "1"])
    assert caps.get("appium:processArguments") == {"args": ["-ChaosBankStartUnlocked", "1"]}
    assert caps.get("appium:forceAppLaunch") is True
    assert caps.get("appium:shouldTerminateApp") is True


def test_no_launch_args_reuses_the_running_app(monkeypatch):
    caps = _build_ios_driver(monkeypatch, None)
    assert "appium:processArguments" not in caps
    assert caps.get("appium:forceAppLaunch") is None
    assert caps.get("appium:shouldTerminateApp") is False
