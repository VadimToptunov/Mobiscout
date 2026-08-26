"""Behaviour tests for the basic security subcommands (`security scan/audit/list/compare`).

These drive the real ``SecurityScanner`` over a minimal in-memory APK/IPA (a real
zip so the stdlib string/zip scanning runs for real), plus the pure ``compare``
report-diff logic over real JSON report files. Only unavoidable heavy tooling
(apktool/androguard) is absent, and the scanner is honest about that — so the
exit codes and rendered summaries under test are genuine.
"""

import json
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.cli.security import security


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _fake_apk(path: Path, entry="classes.dex", content="hello = 1") -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(entry, content)
    return path


# ---------------------------------------------------------------------------- scan


def test_scan_missing_path_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["scan", str(tmp_path / "nope.apk"), "-p", "android", "-n", "App"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "Path not found" in result.output


def test_scan_android_clean_apk_exits_zero(runner, tmp_path):
    apk = _fake_apk(tmp_path / "app.apk")
    result = runner.invoke(security, ["scan", str(apk), "-p", "android", "-n", "App"])
    _no_crash(result)
    # No apktool/bytecode → only an INFO coverage note → no critical/high → exit 0.
    assert result.exit_code == 0
    assert "Security Scan Results" in result.output


def test_scan_writes_report_file(runner, tmp_path):
    apk = _fake_apk(tmp_path / "app.apk")
    out = tmp_path / "report.json"
    result = runner.invoke(security, ["scan", str(apk), "-p", "android", "-n", "App", "-o", str(out), "-f", "json"])
    _no_crash(result)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["app_name"] == "App" and "summary" in data


def test_scan_ios_ipa(runner, tmp_path):
    ipa = _fake_apk(tmp_path / "app.ipa", entry="Info.plist", content="<plist></plist>")
    result = runner.invoke(security, ["scan", str(ipa), "-p", "ios", "-n", "App"])
    _no_crash(result)
    assert "Platform: ios" in result.output


# --------------------------------------------------------------------------- audit


def test_audit_missing_path_exits_one(runner, tmp_path):
    result = runner.invoke(security, ["audit", str(tmp_path / "nope.apk"), "-p", "android", "-n", "App"])
    _no_crash(result)
    assert result.exit_code == 1


def test_audit_renders_findings(runner, tmp_path):
    ipa = _fake_apk(tmp_path / "app.ipa", entry="Info.plist", content="<plist></plist>")
    result = runner.invoke(security, ["audit", str(ipa), "-p", "ios", "-n", "App"])
    _no_crash(result)
    # The real iOS scan emits a MEDIUM binary finding and the INFO coverage note.
    # An audit that rendered nothing would read as a clean bill of health, which is
    # the one thing this scanner must never say by accident.
    assert "PIE Not Enabled" in result.output
    assert "Partial analysis" in result.output


def test_audit_severity_filter_is_applied(runner, tmp_path):
    ipa = _fake_apk(tmp_path / "app.ipa", entry="Info.plist", content="<plist></plist>")
    medium = runner.invoke(security, ["audit", str(ipa), "-p", "ios", "-n", "App", "--severity", "medium"])
    critical = runner.invoke(security, ["audit", str(ipa), "-p", "ios", "-n", "App", "--severity", "critical"])
    _no_crash(medium)
    _no_crash(critical)
    # --severity medium keeps the MEDIUM finding and drops the INFO coverage note...
    assert "PIE Not Enabled" in medium.output
    assert "Partial analysis" not in medium.output
    # ...and nothing here is critical, so that filter renders nothing at all.
    assert "PIE Not Enabled" not in critical.output


# ---------------------------------------------------------------------------- list


def test_list_shows_owasp_categories(runner):
    result = runner.invoke(security, ["list"])
    _no_crash(result)
    assert "M1" in result.output and "Insecure Data Storage" in result.output


# ------------------------------------------------------------------------- compare


def _report(path: Path, counts) -> Path:
    critical, high, medium, low = counts
    path.write_text(
        json.dumps(
            {
                "summary": {
                    "critical": critical,
                    "high": high,
                    "medium": medium,
                    "low": low,
                    "total_findings": critical + high + medium + low,
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_compare_missing_file_exits_one(runner, tmp_path):
    v1 = _report(tmp_path / "v1.json", (0, 0, 0, 0))
    result = runner.invoke(security, ["compare", "App", str(v1), str(tmp_path / "missing.json")])
    _no_crash(result)
    assert result.exit_code == 1
    assert "not found" in result.output


def test_compare_reports_improvement(runner, tmp_path):
    v1 = _report(tmp_path / "v1.json", (2, 3, 1, 0))  # 6 findings
    v2 = _report(tmp_path / "v2.json", (0, 1, 1, 0))  # 2 findings
    result = runner.invoke(security, ["compare", "App", str(v1), str(v2)])
    _no_crash(result)
    assert "Security improved" in result.output


def test_compare_reports_degradation(runner, tmp_path):
    v1 = _report(tmp_path / "v1.json", (0, 0, 1, 0))
    v2 = _report(tmp_path / "v2.json", (1, 2, 1, 0))
    result = runner.invoke(security, ["compare", "App", str(v1), str(v2)])
    _no_crash(result)
    assert "Security degraded" in result.output


def test_compare_reports_no_change(runner, tmp_path):
    v1 = _report(tmp_path / "v1.json", (1, 1, 1, 1))
    v2 = _report(tmp_path / "v2.json", (1, 1, 1, 1))
    result = runner.invoke(security, ["compare", "App", str(v1), str(v2)])
    _no_crash(result)
    assert "No change" in result.output
