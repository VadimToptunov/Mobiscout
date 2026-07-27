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
