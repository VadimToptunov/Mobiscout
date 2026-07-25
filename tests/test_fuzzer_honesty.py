"""The fuzzer used to FABRICATE results — _execute_fuzz / _execute_api_fuzz set
success/crash from random.random(), so "crashes found" were invented. Now UI
fuzzing without a device is honestly flagged simulated (no invented crashes) and
drives a real driver when given one; API fuzzing issues real HTTP requests and
judges the actual response. These pin that no result comes from randomness.
"""

import requests

from framework.fuzzing.fuzzer import APIFuzzer, InputType, UIFuzzer


# ---- UI fuzzing ------------------------------------------------------------
def test_ui_fuzz_without_driver_is_simulated_never_fabricated():
    fuzzer = UIFuzzer()  # no driver
    results = fuzzer.fuzz_text_field("username", InputType.TEXT, count=15)
    assert results and all(r.simulated for r in results)
    assert all(not r.crash for r in results)  # no invented crashes
    assert fuzzer.get_statistics()["crashes"] == 0


class _RaisingDriver:
    def find_element(self, *_a, **_k):
        raise RuntimeError("element not found")


def test_ui_fuzz_with_driver_reports_a_real_crash():
    fuzzer = UIFuzzer(driver=_RaisingDriver())
    results = fuzzer.fuzz_text_field("username", InputType.TEXT, count=3)
    assert all(r.crash and not r.simulated for r in results)
    assert "element not found" in results[0].error


# ---- API fuzzing -----------------------------------------------------------
class _Resp:
    def __init__(self, status):
        self.status_code = status


def test_api_fuzz_5xx_is_a_crash(monkeypatch):
    monkeypatch.setattr(requests, "request", lambda *a, **k: _Resp(500))
    results = APIFuzzer().fuzz_endpoint("GET", "http://api.test/x", InputType.TEXT, count=5)
    assert results and all(r.crash for r in results)  # from the real 500, not random


def test_api_fuzz_2xx_is_success_no_crash(monkeypatch):
    monkeypatch.setattr(requests, "request", lambda *a, **k: _Resp(200))
    results = APIFuzzer().fuzz_endpoint("GET", "http://api.test/x", InputType.TEXT, count=5)
    assert results and all(r.success and not r.crash for r in results)


def test_api_fuzz_timeout_is_a_crash(monkeypatch):
    def _timeout(*a, **k):
        raise requests.exceptions.Timeout("too slow")

    monkeypatch.setattr(requests, "request", _timeout)
    results = APIFuzzer().fuzz_endpoint("GET", "http://api.test/x", InputType.TEXT, count=3)
    assert results and all(r.crash for r in results)
