"""`crawl --record-events` + `mobiscout events` wire the previously-unreachable
EventStore to the product. Recording is derived from a finished CrawlResult (zero
crawl-hot-path cost); these drive the recorder and the reader commands end-to-end.
"""

import pytest
from click.testing import CliRunner

from framework.cli.events_commands import events
from framework.crawler.models import CrawlElement, CrawlResult
from framework.storage.crawl_recorder import record_crawl_session
from framework.storage.event_store import EventStore


def _el(text: str) -> CrawlElement:
    return CrawlElement(
        resource_id="id/x",
        text=text,
        content_desc="",
        class_name="android.widget.Button",
        clickable=True,
        bounds=(0, 0, 10, 10),
    )


def _result() -> CrawlResult:
    return CrawlResult(
        transitions=[
            ("home", _el("Login"), "login"),
            ("login", _el("Submit"), "home"),
        ]
    )


def test_record_crawl_session_writes_ordered_events(tmp_path):
    db = tmp_path / "s.db"
    n = record_crawl_session(_result(), db, "sess1", package="com.x", platform="android")
    assert n == 4  # 2 transitions * (tap + navigation)

    store = EventStore(str(db))
    sessions = store.get_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "sess1"
    assert sessions[0]["event_count"] == 4

    types = [e["event_type"] for e in store.get_events(session_id="sess1", limit=100)]
    assert types == ["ui", "navigation", "ui", "navigation"]


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def recorded_db(tmp_path):
    db = tmp_path / "s.db"
    record_crawl_session(_result(), db, "sess1", package="com.x")
    return db


def test_events_sessions_lists_the_session(runner, recorded_db):
    result = runner.invoke(events, ["sessions", str(recorded_db)])
    assert result.exit_code == 0, result.output
    assert "sess1" in result.output


def test_events_timeline_prints_events(runner, recorded_db):
    result = runner.invoke(events, ["timeline", str(recorded_db)])
    assert result.exit_code == 0, result.output
    assert "navigation" in result.output  # the event-type column rendered


def test_events_stats_runs(runner, recorded_db):
    result = runner.invoke(events, ["stats", str(recorded_db)])
    assert result.exit_code == 0, result.output


def test_events_timeline_aborts_on_empty_db(runner, tmp_path):
    empty = tmp_path / "empty.db"
    EventStore(str(empty))  # create schema, no events
    result = runner.invoke(events, ["timeline", str(empty)])
    assert result.exit_code != 0
