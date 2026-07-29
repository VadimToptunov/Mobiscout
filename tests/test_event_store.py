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


# ------------------------------------------------------------------- bulk ingestion

_BULK_EVENTS = [
    {"sessionId": "s1", "actionType": "tap", "screen": "Home", "timestamp": 100},
    {"sessionId": "s1", "navType": "push", "fromScreen": "Home", "toScreen": "Detail", "timestamp": 200},
    {"sessionId": "s1", "navType": "push", "fromScreen": "Detail", "toScreen": "Home", "timestamp": 300},
    {"sessionId": "s1", "navType": "push", "fromScreen": "Home", "toScreen": "Detail", "timestamp": 400},
    {"sessionId": "s2", "method": "GET", "url": "https://api.x/y", "timestamp": 50},
]


def _screens_map(store, session_id):
    return {s["screen_name"]: s["visit_count"] for s in store.get_screens(session_id)}


def _flows_map(store, session_id):
    return {(f["from_screen"], f["to_screen"]): f["count"] for f in store.get_flows(session_id)}


def test_add_events_bulk_equals_repeated_single_adds(tmp_path):
    """add_events(iterable) must leave the DB in the same state as N add_event calls."""
    single = EventStore(str(tmp_path / "single.db"))
    for event in _BULK_EVENTS:
        single.add_event(event)

    bulk = EventStore(str(tmp_path / "bulk.db"))
    added = bulk.add_events(_BULK_EVENTS)

    assert added == len(_BULK_EVENTS)

    # Same events (compared on stable fields, ignoring autoincrement id / created_at).
    def norm(store):
        return sorted(
            (e["session_id"], e["event_type"], e["timestamp"], e["screen"], json.dumps(e["data"], sort_keys=True))
            for e in store.get_events(limit=10000)
        )

    assert norm(single) == norm(bulk)

    # Same derived screen/flow aggregates and summary statistics.
    for session_id in ("s1", "s2"):
        assert _screens_map(single, session_id) == _screens_map(bulk, session_id)
        assert _flows_map(single, session_id) == _flows_map(bulk, session_id)
    assert single.get_statistics() == bulk.get_statistics()


def test_add_events_opens_a_single_connection(tmp_path, monkeypatch):
    """Bulk ingestion opens exactly one sqlite connection, vs one-per-event before."""
    import framework.storage.event_store as es_mod

    store = EventStore(str(tmp_path / "conn.db"))  # __init__ connections happen first

    real_connect = es_mod.sqlite3.connect
    calls = {"n": 0}

    def counting_connect(*args, **kwargs):
        calls["n"] += 1
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(es_mod.sqlite3, "connect", counting_connect)

    store.add_events(_BULK_EVENTS)
    assert calls["n"] == 1

    # By contrast, the same events via single add_event open one connection each.
    calls["n"] = 0
    for event in _BULK_EVENTS:
        store.add_event(event)
    assert calls["n"] == len(_BULK_EVENTS)


def test_import_from_json_uses_bulk_add(tmp_path, monkeypatch):
    """import_from_json routes through add_events (single connection) and returns count."""
    import framework.storage.event_store as es_mod

    events = [
        {"sessionId": "imp", "actionType": "tap", "timestamp": 1},
        {"sessionId": "imp", "navType": "push", "toScreen": "Next", "timestamp": 2},
        {"sessionId": "imp", "actionType": "tap", "timestamp": 3},
    ]
    path = tmp_path / "events.json"
    path.write_text(json.dumps({"events": events}), encoding="utf-8")

    store = EventStore(str(tmp_path / "imp.db"))

    real_connect = es_mod.sqlite3.connect
    calls = {"n": 0}
    monkeypatch.setattr(
        es_mod.sqlite3,
        "connect",
        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), real_connect(*a, **k))[1],
    )

    n = store.import_from_json(str(path))
    assert n == 3
    assert calls["n"] == 1
    assert len(store.get_events("imp")) == 3
