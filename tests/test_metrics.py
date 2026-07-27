"""Behaviour tests for the observability layer (framework/observability/metrics.py).

These drive the real collector/logger/tracer and assert the concrete artifacts
they produce: aggregated counter values, Prometheus text (HELP/TYPE lines and
escaped labels), the JSON-lines log file on disk, span timing, and the
ObservabilityManager wiring that ties metrics + logging + tracing together.
"""

import json

from framework.observability.metrics import (
    MetricsCollector,
    MetricType,
    ObservabilityManager,
    StructuredLogger,
    TracingContext,
)

# --- MetricsCollector --------------------------------------------------------


def test_inc_counter_accumulates_same_key():
    m = MetricsCollector()
    m.inc_counter("tests_total", labels={"suite": "smoke"})
    m.inc_counter("tests_total", value=2.0, labels={"suite": "smoke"})
    key = m._make_key("tests_total", {"suite": "smoke"})
    assert m.metrics[key].value == 3.0
    assert m.metrics[key].type == MetricType.COUNTER


def test_different_labels_are_distinct_series():
    m = MetricsCollector()
    m.inc_counter("tests_total", labels={"suite": "smoke"})
    m.inc_counter("tests_total", labels={"suite": "regression"})
    assert len(m.metrics) == 2


def test_set_gauge_overwrites_previous_value():
    m = MetricsCollector()
    m.set_gauge("device_availability", 0.5)
    m.set_gauge("device_availability", 0.9)
    assert m.metrics["device_availability"].value == 0.9
    assert m.metrics["device_availability"].type == MetricType.GAUGE


def test_observe_histogram_keeps_all_samples():
    m = MetricsCollector()
    m.observe_histogram("latency", 1.0, labels={"ep": "a"})
    m.observe_histogram("latency", 2.5, labels={"ep": "a"})
    key = m._make_key("latency", {"ep": "a"})
    assert m.histograms[key] == [1.0, 2.5]
    # Latest observation is exported as the metric value.
    assert m.metrics[key].value == 2.5
    assert m.metrics[key].type == MetricType.HISTOGRAM


def test_export_prometheus_format_and_labels():
    m = MetricsCollector()
    m.inc_counter("tests_failed_total", value=4.0, labels={"test": "login"}, help_text="Total failed")
    text = m.export_prometheus()
    assert "# HELP tests_failed_total Total failed" in text
    assert "# TYPE tests_failed_total counter" in text
    assert 'tests_failed_total{test="login"} 4.0' in text
    assert text.endswith("\n")


def test_export_prometheus_writes_file(tmp_path):
    m = MetricsCollector()
    m.set_gauge("healing_success_rate", 0.75, help_text="Rate")
    out = tmp_path / "sub" / "metrics.prom"
    returned = m.export_prometheus(out)
    assert out.exists()
    on_disk = out.read_text(encoding="utf-8")
    assert on_disk == returned
    assert "healing_success_rate 0.75" in on_disk


def test_export_prometheus_no_labels_has_no_braces():
    m = MetricsCollector()
    m.set_gauge("uptime", 1.0)
    text = m.export_prometheus()
    assert "uptime 1.0" in text
    assert "uptime{" not in text


def test_get_summary_counts_by_type():
    m = MetricsCollector()
    m.inc_counter("c1")
    m.set_gauge("g1", 1.0)
    m.observe_histogram("h1", 3.0)
    summary = m.get_summary()
    assert summary["total_metrics"] == 3
    assert summary["counters"] == 1
    assert summary["gauges"] == 1
    assert summary["histograms"] == 1
    names = {entry["name"] for entry in summary["metrics"]}
    assert names == {"c1", "g1", "h1"}


# --- StructuredLogger --------------------------------------------------------


def test_logger_writes_json_lines_with_context(tmp_path):
    log_path = tmp_path / "logs" / "app.json"
    logger = StructuredLogger(log_path)
    logger.add_context(run_id="r1")
    logger.info("started", phase="setup")
    logger.error("boom", code=500)

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["level"] == "INFO"
    assert first["message"] == "started"
    assert first["run_id"] == "r1"  # context merged in
    assert first["phase"] == "setup"
    second = json.loads(lines[1])
    assert second["level"] == "ERROR"
    assert second["code"] == 500


def test_logger_clear_context_drops_fields(tmp_path):
    log_path = tmp_path / "app.json"
    logger = StructuredLogger(log_path)
    logger.add_context(run_id="r1")
    logger.clear_context()
    logger.debug("msg")
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert "run_id" not in entry
    assert entry["level"] == "DEBUG"


# --- TracingContext ----------------------------------------------------------


def test_span_lifecycle_records_duration_and_parenting():
    trace = TracingContext(trace_id="fixed-trace")
    parent = trace.start_span("parent")
    child = trace.start_span("child")
    assert trace.current_span == child
    trace.end_span(child, result="ok")
    # Ending a span restores the parent as current.
    assert trace.current_span == parent
    trace.end_span(parent)
    assert trace.current_span is None

    spans = {s["span_id"]: s for s in trace.spans}
    assert spans[child]["parent_span"] == parent
    assert spans[child]["attributes"]["result"] == "ok"
    assert spans[child]["duration_ms"] is not None and spans[child]["duration_ms"] >= 0
    assert all(s["trace_id"] == "fixed-trace" for s in trace.spans)


def test_export_json_writes_trace(tmp_path):
    trace = TracingContext(trace_id="t42")
    span = trace.start_span("op")
    trace.end_span(span)
    out = tmp_path / "traces" / "trace.json"
    trace.export_json(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["trace_id"] == "t42"
    assert len(data["spans"]) == 1


# --- ObservabilityManager ----------------------------------------------------


def test_manager_records_test_lifecycle(tmp_path):
    mgr = ObservabilityManager()
    mgr.logger = StructuredLogger(tmp_path / "obs.json")
    mgr.start_trace("trace-1")

    mgr.record_test_start("test_login")
    mgr.record_test_end("test_login", status="passed", duration=1.25)

    # Counters for start + passed.
    started = mgr.metrics.metrics[mgr.metrics._make_key("tests_started_total", {"test": "test_login"})]
    passed = mgr.metrics.metrics[mgr.metrics._make_key("tests_passed_total", {"test": "test_login"})]
    assert started.value == 1.0
    assert passed.value == 1.0

    # Histogram sample recorded for duration.
    hist_key = mgr.metrics._make_key("test_duration_seconds", {"status": "passed", "test": "test_login"})
    assert mgr.metrics.histograms[hist_key] == [1.25]

    # Span started and ended with status attribute.
    assert len(mgr.tracing.spans) == 1
    assert mgr.tracing.spans[0]["attributes"]["status"] == "passed"

    # Both log lines written.
    lines = (tmp_path / "obs.json").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_manager_singleton_is_shared():
    ObservabilityManager._instance = None
    a = ObservabilityManager.get_instance()
    b = ObservabilityManager.get_instance()
    assert a is b
    ObservabilityManager._instance = None
