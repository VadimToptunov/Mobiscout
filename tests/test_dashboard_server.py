"""Behaviour tests for the dashboard web server (framework/dashboard/server.py).

httpx / a bound TCP port aren't needed: the FastAPI route handlers are plain
coroutines closing over a real DashboardDB, so we seed a real on-disk SQLite DB
(via DashboardDB) and invoke each endpoint's coroutine directly, asserting the
JSON/HTML it returns. This exercises the real stats aggregation, status
filtering, approve/reject flows and 404 handling.
"""

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from framework.dashboard.models import HealedSelector, HealingStatus, TestResult
from framework.dashboard.server import DashboardServer
from framework.domain import TestStatus


@pytest.fixture()
def server(tmp_path):
    return DashboardServer(tmp_path)


def _endpoint(server, method, path):
    for route in server.app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise KeyError(f"{method} {path} not found")


def _call(coro):
    return asyncio.run(coro)


def _body(response):
    return json.loads(response.body)


class _Req:
    """Minimal stand-in for a Starlette Request — only .headers is read by the origin guard."""

    def __init__(self, origin=None):
        self.headers = {"origin": origin} if origin else {}


def _seed_result(server, name, status, duration=1.0, offset_min=0, rid=None):
    server.db.add_test_result(
        TestResult(
            id=rid or f"{name}-{status.value}-{offset_min}",
            name=name,
            status=status,
            duration=duration,
            timestamp=datetime.now() - timedelta(minutes=offset_min),
            file_path="tests/test_x.py",
        )
    )


def _seed_selector(server, sid, status=HealingStatus.PENDING, confidence=0.9, file_path="pages/login.py"):
    server.db.add_healed_selector(
        HealedSelector(
            id=sid,
            test_name="test_login",
            element_name="login_btn",
            file_path=file_path,
            old_selector_type="id",
            old_selector_value="old_id",
            new_selector_type="accessibility_id",
            new_selector_value="new_id",
            confidence=confidence,
            strategy="ml",
            status=status,
            timestamp=datetime.now(),
        )
    )


def _seed_page_file(server, rel_path="pages/login.py"):
    """Write a Page Object file under the server's repo root carrying the seeded
    selector's old locator, so approve has a real file to rewrite."""
    path = server.repo_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('login_btn = ("id", "old_id")\n', encoding="utf-8")
    return path


# --- HTML rendering ----------------------------------------------------------


def test_dashboard_html_is_rendered():
    import tempfile
    from pathlib import Path

    server = DashboardServer(Path(tempfile.mkdtemp()))
    html = server._get_dashboard_html()
    assert "<!DOCTYPE html>" in html
    assert "Test Maintenance Dashboard" in html
    assert "/api/stats" in html  # the Alpine loader wires the real endpoints
    assert "approveSelector" in html


def test_root_endpoint_serves_html(server):
    resp = _call(_endpoint(server, "GET", "/")())
    assert resp.status_code == 200
    assert b"Test Maintenance Dashboard" in resp.body


# --- /api/stats --------------------------------------------------------------


def test_stats_empty_db(server):
    body = _body(_call(_endpoint(server, "GET", "/api/stats")()))
    assert body["total_tests"] == 0
    assert body["avg_pass_rate"] == 0.0


def test_stats_aggregates_health_and_selectors(server):
    # healthy test: 3/3 passed -> pass_rate 1.0 (passing, not flaky)
    for i in range(3):
        _seed_result(server, "test_healthy", TestStatus.PASSED, offset_min=i)
    # failing test: 0/2 passed -> pass_rate 0.0 (failing)
    for i in range(2):
        _seed_result(server, "test_failing", TestStatus.FAILED, offset_min=i)
    # flaky test: 1 pass / 1 fail -> pass_rate 0.5 (flaky)
    _seed_result(server, "test_flaky", TestStatus.PASSED, offset_min=0)
    _seed_result(server, "test_flaky", TestStatus.FAILED, offset_min=1)

    _seed_selector(server, "s1", HealingStatus.PENDING)
    _seed_selector(server, "s2", HealingStatus.APPROVED)

    body = _body(_call(_endpoint(server, "GET", "/api/stats")()))
    assert body["total_tests"] == 3
    assert body["passing_tests"] == 1
    assert body["failing_tests"] == 1
    assert body["flaky_tests"] == 1
    assert body["healed_selectors_pending"] == 1
    assert body["healed_selectors_approved"] == 1
    assert 0.0 < body["avg_pass_rate"] < 1.0


# --- /api/tests --------------------------------------------------------------


def test_get_tests_filters_by_status(server):
    _seed_result(server, "t_pass", TestStatus.PASSED, rid="p1")
    _seed_result(server, "t_fail", TestStatus.FAILED, rid="f1")

    all_tests = _body(_call(_endpoint(server, "GET", "/api/tests")(limit=100, status=None)))
    assert len(all_tests) == 2

    failed = _body(_call(_endpoint(server, "GET", "/api/tests")(limit=100, status="failed")))
    assert len(failed) == 1
    assert failed[0]["name"] == "t_fail"
    assert failed[0]["status"] == "failed"


def test_get_test_health_returns_metrics(server):
    for i in range(2):
        _seed_result(server, "t_h", TestStatus.PASSED, duration=2.0, offset_min=i)
    health = _body(_call(_endpoint(server, "GET", "/api/tests/health")(days=30)))
    assert len(health) == 1
    assert health[0]["test_name"] == "t_h"
    assert health[0]["total_runs"] == 2
    assert health[0]["pass_rate"] == 1.0


# --- /api/selectors ----------------------------------------------------------


def test_get_selectors_filtered_by_status(server):
    _seed_selector(server, "s_pending", HealingStatus.PENDING)
    _seed_selector(server, "s_approved", HealingStatus.APPROVED)
    pending = _body(_call(_endpoint(server, "GET", "/api/selectors")(status="pending")))
    assert [s["id"] for s in pending] == ["s_pending"]


def test_get_single_selector(server):
    _seed_selector(server, "s1", confidence=0.42)
    body = _body(_call(_endpoint(server, "GET", "/api/selectors/{selector_id}")("s1")))
    assert body["id"] == "s1"
    assert body["confidence"] == 0.42
    assert body["new_selector"]["value"] == "new_id"


def test_get_single_selector_404(server):
    with pytest.raises(HTTPException) as exc:
        _call(_endpoint(server, "GET", "/api/selectors/{selector_id}")("missing"))
    assert exc.value.status_code == 404


# --- approve / reject --------------------------------------------------------


def test_approve_selector_applies_to_file_then_marks_approved(server):
    # Approve must rewrite the source file, not just flip a DB flag.
    page = _seed_page_file(server, "pages/login.py")
    _seed_selector(server, "s1", HealingStatus.PENDING, file_path="pages/login.py")
    body = _body(_call(_endpoint(server, "POST", "/api/selectors/{selector_id}/approve")("s1", _Req())))
    assert body["status"] == "approved" and body["selector_id"] == "s1"
    assert body["file_updated"] is True
    updated = page.read_text(encoding="utf-8")
    assert "new_id" in updated  # the healed value was written into the file
    assert server.db.get_selector("s1").status == HealingStatus.APPROVED


def test_approve_does_not_mark_approved_when_file_update_fails(server):
    # No file on disk → approval cannot be applied → 422, and the DB stays PENDING
    # instead of reporting a success that never touched a file.
    _seed_selector(server, "s1", HealingStatus.PENDING, file_path="pages/missing.py")
    with pytest.raises(HTTPException) as exc:
        _call(_endpoint(server, "POST", "/api/selectors/{selector_id}/approve")("s1", _Req()))
    assert exc.value.status_code == 422
    assert server.db.get_selector("s1").status == HealingStatus.PENDING


def test_approve_rejects_path_escape(server):
    # A poisoned selector row must not overwrite a file outside the repo.
    for bad in ("/etc/passwd", "../../secret.txt"):
        _seed_selector(server, "s1", HealingStatus.PENDING, file_path=bad)
        with pytest.raises(HTTPException) as exc:
            _call(_endpoint(server, "POST", "/api/selectors/{selector_id}/approve")("s1", _Req()))
        assert exc.value.status_code == 400
        assert server.db.get_selector("s1").status == HealingStatus.PENDING


def test_approve_refuses_cross_origin(server):
    _seed_page_file(server, "pages/login.py")
    _seed_selector(server, "s1", HealingStatus.PENDING, file_path="pages/login.py")
    with pytest.raises(HTTPException) as exc:
        _call(_endpoint(server, "POST", "/api/selectors/{selector_id}/approve")("s1", _Req("http://evil.example.com")))
    assert exc.value.status_code == 403
    assert server.db.get_selector("s1").status == HealingStatus.PENDING  # nothing applied


def test_reject_selector_updates_status(server):
    _seed_selector(server, "s1", HealingStatus.PENDING)
    body = _body(_call(_endpoint(server, "POST", "/api/selectors/{selector_id}/reject")("s1", _Req())))
    assert body == {"status": "rejected", "selector_id": "s1"}
    assert server.db.get_selector("s1").status == HealingStatus.REJECTED


def test_approve_missing_selector_404(server):
    with pytest.raises(HTTPException) as exc:
        _call(_endpoint(server, "POST", "/api/selectors/{selector_id}/approve")("nope", _Req()))
    assert exc.value.status_code == 404
