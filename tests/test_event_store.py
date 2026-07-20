"""SQLite event store: ingest SDK observation events (UI / navigation / network),
then query them back by session, screen and type, with derived screen/flow stats
and summary statistics. Exercised against a real on-disk DB in a tmp dir."""

import json

import pytest

from framework.storage.event_store import EventStore


@pytest.fixture()
def store(tmp_path):
    # A file DB (not :memory:) — the store opens a fresh connection per call, so an
    # in-memory DB would be empty on the next one.
    return EventStore(str(tmp_path / "events.db"))


def _seed(store):
    store.add_event({"sessionId": "s1", "actionType": "tap", "screen": "Home", "timestamp": 100})
    store.add_event(
        {"sessionId": "s1", "navType": "push", "fromScreen": "Home", "toScreen": "Detail", "timestamp": 200}
    )
    store.add_event({"sessionId": "s1", "method": "GET", "url": "https://api.x/y", "timestamp": 300})


def test_event_type_is_inferred_from_shape(store):
    _seed(store)
    types = {e["event_type"] for e in store.get_events("s1")}
    assert {"ui", "navigation", "network"} <= types


def test_adding_an_event_creates_its_session(store):
    store.add_event({"sessionId": "abc", "actionType": "tap", "timestamp": 1})
    ids = {s["session_id"] for s in store.get_sessions()}
    assert "abc" in ids


def test_get_events_filters_by_type(store):
    _seed(store)
    ui = store.get_events("s1", event_type="ui")
    assert len(ui) == 1 and ui[0]["event_type"] == "ui"


def test_navigation_records_visited_screen_and_flow(store):
    _seed(store)
    screens = {s["screen_name"] for s in store.get_screens("s1")}
    assert "Detail" in screens
    flows = store.get_flows("s1")
    assert any(f.get("from_screen") == "Home" and f.get("to_screen") == "Detail" for f in flows)


def test_network_events_are_queryable(store):
    _seed(store)
    net = store.get_network_events("s1")
    assert len(net) == 1 and net[0]["event_type"] == "network"


def test_timeline_is_ordered_by_timestamp(store):
    _seed(store)
    ts = [e["timestamp"] for e in store.get_event_timeline("s1")]
    assert ts == sorted(ts)


def test_statistics_count_events(store):
    _seed(store)
    stats = store.get_statistics("s1")
    assert stats["total_events"] == 3


def test_clear_session_removes_its_events(store):
    _seed(store)
    store.clear_session("s1")
    assert store.get_events("s1") == []


def test_clear_all_empties_the_store(store):
    _seed(store)
    store.add_event({"sessionId": "s2", "actionType": "tap", "timestamp": 5})
    store.clear_all()
    assert store.get_sessions() == []


def test_import_from_json_ingests_a_list_of_events(store, tmp_path):
    events = [
        {"sessionId": "imp", "actionType": "tap", "timestamp": 1},
        {"sessionId": "imp", "navType": "push", "toScreen": "Next", "timestamp": 2},
    ]
    path = tmp_path / "events.json"
    path.write_text(json.dumps({"events": events}), encoding="utf-8")  # export wraps events in a dict
    n = store.import_from_json(str(path))
    assert n == 2
    assert len(store.get_events("imp")) == 2


def test_unknown_shape_is_typed_unknown(store):
    store.add_event({"sessionId": "s1", "timestamp": 1})
    assert store.get_events("s1", event_type="unknown")
