"""EventCorrelator: Python-fallback correlation of UI, API, and navigation events."""

import pytest

from framework.correlation.correlator import EventCorrelator
from framework.correlation.types import (
    CorrelationResult,
    CorrelationStrength,
    CorrelationMethod,
    UIToAPICorrelation,
    APIToNavigationCorrelation,
)
from framework.storage.event_store import EventStore


@pytest.fixture
def correlator():
    """A correlator forced onto the pure-Python path (no Rust)."""
    return EventCorrelator(force_python=True)


def _ui(event_id="ui1", ts=1000, action="tap", screen="LoginScreen", **extra):
    ev = {
        "eventId": event_id,
        "action": action,
        "screen": screen,
        "timestamp": ts,
        "elementId": "login_button",
    }
    ev.update(extra)
    return ev


def _api(event_id="api1", ts=1100, method="POST", url="/auth/login", status=200, **extra):
    ev = {
        "eventId": event_id,
        "method": method,
        "url": url,
        "statusCode": status,
        "timestamp": ts,
        "duration": 50,
    }
    ev.update(extra)
    return ev


def _nav(event_id="nav1", ts=1300, from_screen="LoginScreen", to_screen="HomeScreen", **extra):
    ev = {
        "eventId": event_id,
        "fromScreen": from_screen,
        "toScreen": to_screen,
        "timestamp": ts,
    }
    ev.update(extra)
    return ev


# --- construction -----------------------------------------------------------


def test_force_python_disables_rust_engine():
    corr = EventCorrelator(force_python=True)
    assert corr.use_rust is False
    assert not hasattr(corr, "rust_correlator")


def test_strategies_are_initialized_with_expected_time_window():
    corr = EventCorrelator(force_python=True)
    assert corr.nav_strategy.max_time_delta_ms == 3000


# --- correlate_session ------------------------------------------------------


def test_correlate_session_without_event_store_raises():
    corr = EventCorrelator(force_python=True)
    with pytest.raises(ValueError, match="EventStore required"):
        corr.correlate_session("session-x")


def test_correlate_events_with_no_events_yields_empty_result(correlator):
    result = correlator.correlate_events("s1", [], [], [])
    assert result.total_ui_events == 0
    assert result.total_api_events == 0
    assert result.total_navigation_events == 0
    assert result.ui_to_api == []
    assert result.correlation_rate == 0.0


def test_correlate_events_records_event_totals(correlator):
    result = correlator.correlate_events("s1", [_ui()], [_api()], [_nav()])
    assert result.total_ui_events == 1
    assert result.total_api_events == 1
    assert result.total_navigation_events == 1


# --- UI -> API correlation --------------------------------------------------


def test_ui_to_api_captures_time_delta_to_first_api(correlator):
    ui = _ui(ts=1000, correlationId="abc")
    api = _api(ts=1250, correlationId="abc")
    result = correlator.correlate_events("s1", [ui], [api], [])
    assert result.ui_to_api[0].time_delta_ms == 250


def test_uncorrelated_ui_and_api_yield_no_correlation(correlator):
    # API happens BEFORE the UI event -> temporal strategy rejects it, and no
    # other shared signal exists, so nothing correlates.
    ui = _ui(ts=5000)
    api = _api(ts=1000)
    result = correlator.correlate_events("s1", [ui], [api], [])
    assert result.ui_to_api == []
    assert result.correlated_ui_events == 0
    assert result.correlation_rate == 0.0


def test_correlation_rate_is_fraction_of_correlated_ui_events(correlator):
    ui_hit = _ui(event_id="ui_hit", ts=1000, correlationId="abc")
    ui_miss = _ui(event_id="ui_miss", ts=9000)
    api = _api(ts=1100, correlationId="abc")
    result = correlator.correlate_events("s1", [ui_hit, ui_miss], [api], [])

    assert result.correlated_ui_events == 1
    assert result.correlation_rate == pytest.approx(0.5)


def test_weak_temporal_correlation_preserves_measured_confidence(correlator):
    # A distant-but-in-window temporal match gives WEAK strength and a low,
    # non-zero confidence that must be preserved (not overwritten to 0.0).
    ui = _ui(ts=1000)
    api = _api(ts=3500)  # 2500ms later -> WEAK, confidence halved by strategy
    result = correlator.correlate_events("s1", [ui], [api], [])

    assert len(result.ui_to_api) == 1
    c = result.ui_to_api[0]
    assert c.strength == CorrelationStrength.WEAK
    assert 0.0 < c.confidence_score < 0.5


def test_correlated_api_events_dedupes_shared_api_id(correlator):
    ui_a = _ui(event_id="uiA", ts=1000, correlationId="abc")
    ui_b = _ui(event_id="uiB", ts=1000, correlationId="abc")
    api = _api(event_id="api1", ts=1100, correlationId="abc")
    result = correlator.correlate_events("s1", [ui_a, ui_b], [api], [])

    # Both UI events correlate to the same API id -> counted once.
    assert result.correlated_ui_events == 2
    assert result.correlated_api_events == 1


# --- API -> Navigation correlation ------------------------------------------


def test_success_status_yields_success_condition(correlator):
    api = _api(ts=1000, status=200, screen="LoginScreen")
    nav = _nav(ts=1300)
    result = correlator.correlate_events("s1", [], [api], [nav])

    assert len(result.api_to_navigation) == 1
    n = result.api_to_navigation[0]
    assert n.condition == "success"
    assert n.time_delta_ms == 300
    assert n.from_screen == "LoginScreen"
    assert n.to_screen == "HomeScreen"


def test_error_status_yields_error_condition(correlator):
    api = _api(ts=1000, status=500)
    nav = _nav(ts=1200)
    result = correlator.correlate_events("s1", [], [api], [nav])
    assert result.api_to_navigation[0].condition == "error"


def test_redirect_status_yields_no_condition(correlator):
    api = _api(ts=1000, status=302)
    nav = _nav(ts=1200)
    result = correlator.correlate_events("s1", [], [api], [nav])
    assert result.api_to_navigation[0].condition is None


def test_navigation_before_api_is_ignored(correlator):
    api = _api(ts=2000)
    nav = _nav(ts=1000)  # navigation precedes the API response
    result = correlator.correlate_events("s1", [], [api], [nav])
    assert result.api_to_navigation == []


def test_navigation_beyond_three_seconds_is_ignored(correlator):
    api = _api(ts=1000)
    nav = _nav(ts=5000)  # 4s later, outside the 3s window
    result = correlator.correlate_events("s1", [], [api], [nav])
    assert result.api_to_navigation == []


# --- full flows -------------------------------------------------------------


def test_full_flow_links_ui_api_and_navigation(correlator):
    ui = _ui(ts=1000, action="tap", screen="LoginScreen", correlationId="abc")
    api = _api(event_id="api1", ts=1100, correlationId="abc")
    nav = _nav(ts=1300)
    result = correlator.correlate_events("s1", [ui], [api], [nav])

    assert len(result.full_flows) == 1
    flow = result.full_flows[0]
    assert flow.flow_id == "flow_ui1"
    assert flow.flow_name == "tap_on_LoginScreen"
    assert len(flow.api_navigation_correlations) == 1
    assert "User tap on LoginScreen" in flow.description
    assert "POST /auth/login" in flow.description
    assert "navigate to HomeScreen" in flow.description


def test_full_flow_without_navigation_uses_ui_correlation_values(correlator):
    ui = _ui(ts=1000, correlationId="abc")
    api = _api(ts=1100, correlationId="abc")
    result = correlator.correlate_events("s1", [ui], [api], [])

    assert len(result.full_flows) == 1
    flow = result.full_flows[0]
    assert flow.api_navigation_correlations == []
    assert flow.overall_strength == result.ui_to_api[0].strength
    assert flow.overall_confidence == pytest.approx(result.ui_to_api[0].confidence_score)


def test_no_ui_correlations_means_no_full_flows(correlator):
    result = correlator.correlate_events("s1", [], [_api()], [_nav()])
    assert result.full_flows == []


# --- statistics -------------------------------------------------------------


def test_statistics_report_counts_and_strong_correlations(correlator):
    ui = _ui(ts=1000, correlationId="abc")
    api = _api(ts=1100, correlationId="abc")
    nav = _nav(ts=1300)
    result = correlator.correlate_events("s1", [ui], [api], [nav])

    stats = result.statistics
    assert stats["ui_to_api_count"] == 1
    assert stats["api_to_nav_count"] == 1
    assert stats["full_flows_count"] == 1
    assert stats["strong_correlations"] == 1


# --- flow description edge cases --------------------------------------------


def test_flow_description_limits_to_first_two_apis(correlator):
    corr = correlator
    ui_corr = UIToAPICorrelation(
        ui_event_id="ui1",
        ui_event_type="tap",
        ui_screen="Home",
        ui_timestamp=0,
        api_calls=[
            {"method": "GET", "endpoint": "/a"},
            {"method": "GET", "endpoint": "/b"},
            {"method": "GET", "endpoint": "/c"},
        ],
        strength=CorrelationStrength.WEAK,
        confidence_score=0.4,
    )
    desc = corr._generate_flow_description(ui_corr, [])
    assert "/a" in desc and "/b" in desc
    assert "/c" not in desc


# --- _event_to_dict ---------------------------------------------------------


def test_event_to_dict_passes_through_plain_dict(correlator):
    ev = {"eventId": "x"}
    assert correlator._event_to_dict(ev) is ev


def test_event_to_dict_handles_pydantic_model(correlator):
    model = APIToNavigationCorrelation(
        api_event_id="a",
        api_method="GET",
        api_endpoint="/x",
        api_status_code=200,
        api_timestamp=1,
        navigation_event_id="n",
        from_screen="A",
        to_screen="B",
        navigation_timestamp=2,
        strength=CorrelationStrength.WEAK,
        confidence_score=0.5,
        time_delta_ms=1,
    )
    out = correlator._event_to_dict(model)
    assert out["api_endpoint"] == "/x"


def test_event_to_dict_handles_keys_mapping(correlator):
    class RowLike:
        def __init__(self, data):
            self._data = data

        def keys(self):
            return self._data.keys()

        def __getitem__(self, key):
            return self._data[key]

    row = RowLike({"eventId": "r1", "timestamp": 5})
    assert correlator._event_to_dict(row) == {"eventId": "r1", "timestamp": 5}


def test_event_to_dict_unknown_object_falls_back_to_empty(correlator):
    class Opaque:
        pass

    assert correlator._event_to_dict(Opaque()) == {}
