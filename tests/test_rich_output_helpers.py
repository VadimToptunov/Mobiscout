"""Unit tests for the shared CLI output helpers in ``framework.cli.rich_output``:
the ``write_report`` format dispatcher and the ``render_comparison`` diff/verdict
renderer that the security and accessibility ``compare`` commands route through."""

import json

from framework.cli import rich_output
from framework.cli.rich_output import ComparisonMetric, render_comparison, write_report


def _capture(func) -> str:
    """Run ``func`` and return everything printed to the shared console."""
    with rich_output.console.capture() as cap:
        func()
    return cap.get()


# --------------------------------------------------------------------- write_report


def test_write_report_json_fallback_matches_json_dump(tmp_path):
    out = tmp_path / "report.json"
    data = {"b": 2, "a": 1, "nested": [1, 2, {"x": True}]}

    write_report(data, out, "json")

    # Default (no writer for "json") serialises exactly like the old inline
    # json.dump(..., indent=2, default=str) blocks.
    assert out.read_text(encoding="utf-8") == json.dumps(data, indent=2, default=str)
    assert json.loads(out.read_text(encoding="utf-8")) == data


def test_write_report_json_fallback_uses_default_str(tmp_path):
    from pathlib import Path

    out = tmp_path / "report.json"
    # A non-JSON-native value must be coerced via ``default=str``.
    write_report({"path": Path("/tmp/x")}, out, "json")
    assert json.loads(out.read_text(encoding="utf-8")) == {"path": "/tmp/x"}


def test_write_report_dispatches_to_matching_writer(tmp_path):
    out = tmp_path / "report.html"
    seen = {}

    def html_writer(path):
        seen["path"] = path
        path.write_text("<html>ok</html>", encoding="utf-8")

    write_report({"ignored": True}, out, "html", {"html": html_writer})

    assert seen["path"] == out
    assert out.read_text(encoding="utf-8") == "<html>ok</html>"


def test_write_report_selects_correct_writer_among_several(tmp_path):
    out = tmp_path / "report.sarif"
    calls = []

    writers = {
        "sarif": lambda p: (calls.append("sarif"), p.write_text("SARIF", encoding="utf-8")),
        "html": lambda p: (calls.append("html"), p.write_text("HTML", encoding="utf-8")),
    }
    write_report({"x": 1}, out, "sarif", writers)

    assert calls == ["sarif"]
    assert out.read_text(encoding="utf-8") == "SARIF"


def test_write_report_unlisted_format_falls_back_to_json(tmp_path):
    out = tmp_path / "report.json"
    # "json" is not in ``writers`` -> JSON fallback, writer left untouched.
    write_report({"x": 1}, out, "json", {"html": lambda p: p.write_text("HTML")})
    assert json.loads(out.read_text(encoding="utf-8")) == {"x": 1}


# ----------------------------------------------------------------- render_comparison


def test_render_comparison_improved_verdict_for_higher_is_better():
    report_a = {"compliance_score": 80.0, "violations": 5, "critical": 2, "serious": 3}
    report_b = {"compliance_score": 92.0, "violations": 1, "critical": 0, "serious": 1}

    out = _capture(
        lambda: render_comparison(
            report_a,
            report_b,
            [
                ComparisonMetric("compliance_score", higher_is_better=True, percent=True),
                ComparisonMetric("violations"),
                ComparisonMetric("critical"),
                ComparisonMetric("serious"),
            ],
            title="[bold cyan]Accessibility Comparison[/bold cyan]",
            columns=("Metric", "Report 1", "Report 2"),
            verdict_key="compliance_score",
            verdict_higher_is_better=True,
            verdict_improved="IMPROVED-VERDICT",
            verdict_degraded="DEGRADED-VERDICT",
            verdict_unchanged="UNCHANGED-VERDICT",
        )
    )

    assert "IMPROVED-VERDICT" in out
    assert "DEGRADED-VERDICT" not in out
    assert "UNCHANGED-VERDICT" not in out
    # Metric label derives from the key via replace("_", " ").title().
    assert "Compliance Score" in out
    # Change column rendered the percent-formatted score delta.
    assert "+12.0%" in out


def test_render_comparison_degraded_verdict_for_lower_is_better():
    report_a = {"critical": 0, "high": 1, "medium": 0, "low": 0, "total_findings": 1}
    report_b = {"critical": 2, "high": 1, "medium": 0, "low": 0, "total_findings": 3}

    out = _capture(
        lambda: render_comparison(
            report_a,
            report_b,
            [
                ComparisonMetric("critical"),
                ComparisonMetric("high"),
                ComparisonMetric("medium"),
                ComparisonMetric("low"),
            ],
            title="[bold cyan]Security Comparison[/bold cyan]",
            columns=("Severity", "Version 1", "Version 2"),
            verdict_key="total_findings",
            verdict_higher_is_better=False,
            verdict_improved="IMPROVED-VERDICT",
            verdict_degraded="DEGRADED-VERDICT",
            verdict_unchanged="UNCHANGED-VERDICT",
        )
    )

    assert "DEGRADED-VERDICT" in out
    assert "IMPROVED-VERDICT" not in out
    # count delta rendered with an explicit sign
    assert "+2" in out


def test_render_comparison_unchanged_verdict_and_dim_zero():
    report = {"critical": 1, "high": 0, "medium": 0, "low": 0, "total_findings": 1}

    out = _capture(
        lambda: render_comparison(
            report,
            dict(report),
            [ComparisonMetric("critical"), ComparisonMetric("high")],
            title="Cmp",
            columns=("Severity", "V1", "V2"),
            verdict_key="total_findings",
            verdict_higher_is_better=False,
            verdict_improved="IMPROVED-VERDICT",
            verdict_degraded="DEGRADED-VERDICT",
            verdict_unchanged="UNCHANGED-VERDICT",
        )
    )

    assert "UNCHANGED-VERDICT" in out
    assert "IMPROVED-VERDICT" not in out
    assert "DEGRADED-VERDICT" not in out
