"""API + log analyzers: pattern/error/timing analysis and assertion generation
over captured calls and logs. Pure data crunching, so tests feed synthetic
calls/logs and assert the analysis — the module had no tests."""

import json
from datetime import datetime, timedelta

from framework.api_analyzer.api_log_analyzer import (
    APIAnalyzer,
    APICall,
    APIMethod,
    LogAnalyzer,
    LogEntry,
    LogLevel,
)

_T0 = datetime(2026, 1, 1, 12, 0, 0)


def _call(url, method=APIMethod.GET, status=200, dur=100.0, ui=None, offset=0):
    return APICall(
        timestamp=_T0 + timedelta(seconds=offset),
        method=method,
        url=url,
        request_headers={"Accept": "application/json"},
        response_status=status,
        duration_ms=dur,
        ui_context=ui,
    )


def _analyzer(calls):
    a = APIAnalyzer()
    for c in calls:
        a.add_api_call(c)
    return a


# ---- APIAnalyzer ----


def test_analyze_patterns_counts_and_timing():
    a = _analyzer(
        [
            _call("/api/users", status=200, dur=100),
            _call("/api/users", status=200, dur=300),
            _call("/api/orders", method=APIMethod.POST, status=500, dur=2000),
        ]
    )
    res = a.analyze_patterns()
    assert res["total_calls"] == 3
    assert res["by_method"]["GET"] == 2 and res["by_method"]["POST"] == 1
    assert res["by_status"][200] == 2 and res["by_status"][500] == 1
    assert res["avg_response_time"] == (100 + 300 + 2000) / 3
    assert len(res["errors"]) == 1 and res["errors"][0]["status"] == 500
    assert len(res["slow_calls"]) == 1  # the 2000ms call


def test_normalize_endpoint_collapses_ids_and_query():
    a = APIAnalyzer()
    assert a._normalize_endpoint("/api/users/123?page=2") == "/api/users/{id}"
    # A uuid segment collapses to {uuid} (using one that doesn't start with a
    # digit, so the numeric-id rule doesn't grab its leading chars first).
    assert a._normalize_endpoint("/api/x/ab34cd12-56ef-78ab-90cd-1234567890ab") == "/api/x/{uuid}"


def test_by_endpoint_groups_normalized():
    a = _analyzer([_call("/api/users/1"), _call("/api/users/2"), _call("/api/users/3")])
    res = a.analyze_patterns()
    assert res["by_endpoint"]["/api/users/{id}"] == 3


def test_generate_assertions_status_and_time():
    a = _analyzer([_call("/api/users", status=200, dur=100) for _ in range(5)])
    asserts = a.generate_assertions(min_confidence=0.7)
    kinds = {x.assertion_type for x in asserts}
    assert "status_code" in kinds and "response_time" in kinds
    status = next(x for x in asserts if x.assertion_type == "status_code")
    assert status.expected_value == 200 and status.confidence == 1.0


def test_generate_assertions_skips_low_confidence_status():
    # 5 different statuses -> most-common confidence 1/5 < 0.7 -> no status assertion
    a = _analyzer([_call("/api/x", status=200 + i, dur=None) for i in range(5)])
    asserts = a.generate_assertions(min_confidence=0.7)
    assert not any(x.assertion_type == "status_code" for x in asserts)


def test_correlate_with_ui():
    a = _analyzer([_call("/a", ui="LoginScreen"), _call("/b", ui="LoginScreen"), _call("/c", ui="Home")])
    assert len(a.correlate_with_ui("LoginScreen")) == 2
    assert a.correlate_with_ui("Nope") == []


def test_export_har(tmp_path):
    a = _analyzer([_call("/api/users", status=200, dur=120)])
    out = tmp_path / "out.har"
    a.export_har(out)
    har = json.loads(out.read_text())
    assert har["log"]["creator"]["name"] == "Mobiscout"
    assert har["log"]["entries"][0]["request"]["url"] == "/api/users"


# ---- LogAnalyzer ----


def _log(msg, level=LogLevel.INFO, offset=0):
    return LogEntry(timestamp=_T0 + timedelta(seconds=offset), level=level, message=msg, source="logcat")


def test_detect_patterns_groups_and_flags_errors():
    la = LogAnalyzer()
    la.add_logs([_log("User 1 logged in"), _log("User 2 logged in"), _log("User 3 logged in")])
    la.add_logs([_log("NullPointerException at line 5", level=LogLevel.ERROR) for _ in range(3)])
    patterns = la.detect_patterns(min_occurrences=3)
    assert len(patterns) == 2
    err = next(p for p in patterns if p.is_error)
    assert err.count == 3 and len(err.examples) == 3


def test_detect_patterns_respects_min_occurrences():
    la = LogAnalyzer()
    la.add_logs([_log("rare event")])  # only once
    assert la.detect_patterns(min_occurrences=3) == []


def test_find_errors_and_warnings():
    la = LogAnalyzer()
    la.add_logs([_log("ok"), _log("bad", LogLevel.ERROR), _log("careful", LogLevel.WARNING)])
    assert len(la.find_errors()) == 1
    assert len(la.find_warnings()) == 1


def test_analyze_timeframe():
    la = LogAnalyzer()
    la.add_logs([_log("a", offset=0), _log("b", LogLevel.ERROR, offset=10), _log("c", offset=100)])
    res = la.analyze_timeframe(_T0, _T0 + timedelta(seconds=20))
    assert res["total"] == 2 and res["errors"] == 1
