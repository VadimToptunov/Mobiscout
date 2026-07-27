"""Behaviour tests for the ``a11y`` CLI group (WCAG accessibility scanning).

Real UI-hierarchy JSON fixtures are scanned end-to-end: the ``scan`` command's
exit code encodes severity (2=critical, 1=serious, 0=clean), and its JSON report
round-trips through ``summary`` and ``compare``. ``audit`` and its severity filter
run against the same fixtures.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.a11y_commands import a11y


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


# A hierarchy with a too-small touch target + an image with no content description:
# guaranteed to raise violations so the report/exit-code paths actually run.
_HIER = {
    "id": "root",
    "type": "View",
    "children": [
        {
            "id": "tiny_btn",
            "class": "android.widget.Button",
            "text": "Go",
            "clickable": True,
            "bounds": {"x": 0, "y": 0, "width": 20, "height": 20},
        },
        {
            "id": "img",
            "class": "android.widget.ImageView",
            "clickable": True,
            "bounds": {"x": 0, "y": 30, "width": 100, "height": 100},
        },
    ],
}


def _hier_file(tmp_path: Path) -> str:
    p = tmp_path / "hierarchy.json"
    p.write_text(json.dumps(_HIER), encoding="utf-8")
    return str(p)


def test_scan_writes_report_and_encodes_severity_in_exit_code(runner, tmp_path):
    report = tmp_path / "report.json"
    result = runner.invoke(
        a11y,
        ["scan", _hier_file(tmp_path), "-a", "MyApp", "-s", "Home", "-o", str(report), "-f", "json"],
    )
    _no_crash(result)
    # Violations present -> non-zero exit (1 serious / 2 critical), never a crash.
    assert result.exit_code in (1, 2)
    assert report.exists()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["app_name"] == "MyApp" and data["screen_name"] == "Home"
    assert data["summary"]["violations"] == len(data["violations"]) > 0


def test_scan_missing_file_exits_one(runner, tmp_path):
    result = runner.invoke(a11y, ["scan", str(tmp_path / "nope.json"), "-a", "A", "-s", "S"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "File not found" in result.output


def test_scan_html_format_writes_report(runner, tmp_path):
    report = tmp_path / "report.html"
    result = runner.invoke(a11y, ["scan", _hier_file(tmp_path), "-a", "A", "-s", "S", "-o", str(report), "-f", "html"])
    _no_crash(result)
    assert report.exists()
    assert "<html" in report.read_text(encoding="utf-8").lower()


def test_summary_reads_scan_report(runner, tmp_path):
    report = tmp_path / "report.json"
    runner.invoke(a11y, ["scan", _hier_file(tmp_path), "-a", "MyApp", "-s", "Home", "-o", str(report)])
    result = runner.invoke(a11y, ["summary", str(report)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "MyApp" in result.output and "Compliance Score" in result.output


def test_summary_missing_file_exits_one(runner, tmp_path):
    result = runner.invoke(a11y, ["summary", str(tmp_path / "nope.json")])
    _no_crash(result)
    assert result.exit_code == 1


def test_audit_prints_violation_details(runner, tmp_path):
    result = runner.invoke(a11y, ["audit", _hier_file(tmp_path), "-a", "MyApp", "-s", "Home"])
    _no_crash(result)
    assert result.exit_code == 0
    # Each violation panel carries a WCAG reference + a recommendation.
    assert "WCAG" in result.output and "Recommendation" in result.output


def test_audit_severity_filter_runs(runner, tmp_path):
    result = runner.invoke(a11y, ["audit", _hier_file(tmp_path), "-a", "MyApp", "-s", "Home", "--severity", "critical"])
    _no_crash(result)
    assert result.exit_code == 0


def test_list_shows_known_checks(runner):
    result = runner.invoke(a11y, ["list"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "color-contrast" in result.output
    assert "touch-target-size" in result.output


def test_compare_two_reports(runner, tmp_path):
    r1 = tmp_path / "r1.json"
    r2 = tmp_path / "r2.json"
    runner.invoke(a11y, ["scan", _hier_file(tmp_path), "-a", "A", "-s", "S", "-o", str(r1)])
    runner.invoke(a11y, ["scan", _hier_file(tmp_path), "-a", "A", "-s", "S", "-o", str(r2)])

    result = runner.invoke(a11y, ["compare", str(r1), str(r2)])
    _no_crash(result)
    assert result.exit_code == 0
    assert "Accessibility Comparison" in result.output
    # Identical reports -> no change verdict.
    assert "No change" in result.output


def test_compare_missing_report_exits_one(runner, tmp_path):
    r1 = tmp_path / "r1.json"
    runner.invoke(a11y, ["scan", _hier_file(tmp_path), "-a", "A", "-s", "S", "-o", str(r1)])
    result = runner.invoke(a11y, ["compare", str(r1), str(tmp_path / "missing.json")])
    _no_crash(result)
    assert result.exit_code == 1
