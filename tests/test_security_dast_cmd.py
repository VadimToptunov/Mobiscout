"""Behaviour tests for the DAST security subcommands (`security dast/ssl/api`).

These commands drive a live network target through ``DASTAnalyzer`` (real
sockets/SSL), which cannot run in a unit test. We therefore stub *only* that
network boundary — returning real ``DASTResult`` / ``SSLAnalysisResult`` /
``APITestResult`` objects populated with real ``DASTFinding`` dataclasses — and
assert the CLI's own logic end-to-end: the findings tables, per-format report
export, the "all clear" path, and the severity-driven exit codes.
"""

import pytest
from click.testing import CliRunner

from framework.cli.security import security
from framework.security.dast.base import (
    DASTFinding,
    DASTResult,
    SSLAnalysisResult,
    APITestResult,
)
from framework.security.dast.base import DASTTestType
from framework.security.types import Severity


@pytest.fixture()
def runner():
    return CliRunner()


def _no_crash(result):
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"command crashed: {result.exception!r}\n{result.output}"


def _finding(severity, title="Weak TLS 1.0 enabled", test_type=DASTTestType.SSL_TLS):
    return DASTFinding(
        test_type=test_type,
        severity=severity,
        title=title,
        description="A weak protocol/cipher was negotiated by the server.",
        evidence="Negotiated TLSv1.0",
        recommendation="Disable TLS < 1.2 and re-test the endpoint configuration thoroughly.",
    )


class _FakeAnalyzer:
    """Stand-in for DASTAnalyzer whose network methods return canned results."""

    result = DASTResult(findings=[], target="", port=443)
    ssl_result = SSLAnalysisResult()
    api_result = APITestResult()

    def analyze(self, target, port=443):
        r = type(self).result
        r.target, r.port = target, port
        return r

    def analyze_ssl(self, host, port=443):
        return type(self).ssl_result

    def test_api(self, base_url, headers=None, endpoints=None):
        return type(self).api_result

    def export_html(self, result, output_path):
        # Delegate to the real (pure, no-network) HTML formatter.
        from framework.security.dast.analyzer import DASTAnalyzer as _Real

        _Real.export_html(self, result, output_path)


@pytest.fixture()
def patch_analyzer(monkeypatch):
    # NB: `framework.cli.security.dast` as an attribute of the security package
    # is the *command* object (re-exported), so fetch the real module via
    # importlib (sys.modules) and patch its DASTAnalyzer global directly.
    import importlib

    dast_mod = importlib.import_module("framework.cli.security.dast")

    def _apply(**attrs):
        for k, v in attrs.items():
            setattr(_FakeAnalyzer, k, v)
        monkeypatch.setattr(dast_mod, "DASTAnalyzer", _FakeAnalyzer)

    yield _apply
    # reset defaults so cases don't leak into each other
    _FakeAnalyzer.result = DASTResult(findings=[], target="", port=443)
    _FakeAnalyzer.ssl_result = SSLAnalysisResult()
    _FakeAnalyzer.api_result = APITestResult()


# --------------------------------------------------------------------------- dast


def test_dast_no_findings_exits_zero(runner, patch_analyzer):
    patch_analyzer(result=DASTResult(findings=[], target="api.example.com"))
    result = runner.invoke(security, ["dast", "api.example.com"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No vulnerabilities found" in result.output


def test_dast_critical_finding_exits_two(runner, patch_analyzer):
    patch_analyzer(result=DASTResult(findings=[_finding(Severity.CRITICAL)], target="h"))
    result = runner.invoke(security, ["dast", "h"])
    _no_crash(result)
    assert result.exit_code == 2  # a critical finding maps to exit code 2


def test_dast_noncritical_finding_exits_one(runner, patch_analyzer):
    patch_analyzer(result=DASTResult(findings=[_finding(Severity.MEDIUM)], target="h"))
    result = runner.invoke(security, ["dast", "h"])
    _no_crash(result)
    assert result.exit_code == 1


def test_dast_writes_json_report(runner, patch_analyzer, tmp_path):
    patch_analyzer(result=DASTResult(findings=[_finding(Severity.HIGH)], target="h"))
    out = tmp_path / "dast.json"
    result = runner.invoke(security, ["dast", "h", "-o", str(out), "-f", "json"])
    _no_crash(result)
    assert out.exists()
    import json

    data = json.loads(out.read_text())
    assert data["findings"] and data["findings"][0]["severity"] == "high"


def test_dast_writes_html_report(runner, patch_analyzer, tmp_path):
    patch_analyzer(result=DASTResult(findings=[_finding(Severity.LOW)], target="h"))
    out = tmp_path / "dast.html"
    result = runner.invoke(security, ["dast", "h", "-o", str(out), "-f", "html"])
    _no_crash(result)
    assert out.exists()
    assert "<html>" in out.read_text().lower()


# ---------------------------------------------------------------------------- ssl


def test_ssl_clean_reports_connection_details(runner, patch_analyzer):
    patch_analyzer(
        ssl_result=SSLAnalysisResult(
            findings=[], protocol="TLSv1.3", cipher_suite="TLS_AES_256", cert_expiry="Jan 1 2030"
        )
    )
    result = runner.invoke(security, ["ssl", "api.example.com"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "TLSv1.3" in result.output


def test_ssl_with_findings_exits_one(runner, patch_analyzer):
    patch_analyzer(ssl_result=SSLAnalysisResult(findings=[_finding(Severity.HIGH)]))
    result = runner.invoke(security, ["ssl", "api.example.com", "--port", "8443"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "SSL/TLS issue" in result.output


# ---------------------------------------------------------------------------- api


def test_api_no_findings_exits_zero(runner, patch_analyzer):
    patch_analyzer(api_result=APITestResult(findings=[], base_url="https://api.example.com"))
    result = runner.invoke(security, ["api", "https://api.example.com"])
    _no_crash(result)
    assert result.exit_code == 0
    assert "No API security issues" in result.output


def test_api_with_finding_exits_one_and_shows_endpoint(runner, patch_analyzer):
    f = _finding(Severity.HIGH, title="SQL Injection", test_type=DASTTestType.API)
    f.endpoint = "/users"
    f.method = "GET"
    f.vulnerability_type = "sql_injection"
    patch_analyzer(api_result=APITestResult(findings=[f], base_url="https://api.example.com"))
    result = runner.invoke(security, ["api", "https://api.example.com", "-a", "Bearer t"])
    _no_crash(result)
    assert result.exit_code == 1
    assert "/users" in result.output and "SQL Injection" in result.output


def test_api_reads_endpoints_file(runner, monkeypatch, tmp_path):
    # The command loads a JSON endpoints file when it exists; assert it is read.
    seen = {}

    class _Recorder(_FakeAnalyzer):
        def test_api(self, base_url, headers=None, endpoints=None):
            seen["endpoints"] = endpoints
            seen["headers"] = headers
            return APITestResult(findings=[])

    ep = tmp_path / "endpoints.json"
    ep.write_text('[{"path": "/health", "method": "GET"}]', encoding="utf-8")
    import importlib

    dast_mod = importlib.import_module("framework.cli.security.dast")
    monkeypatch.setattr(dast_mod, "DASTAnalyzer", _Recorder)
    result = runner.invoke(security, ["api", "https://api.example.com", "-a", "Bearer x", "-e", str(ep)])
    _no_crash(result)
    assert seen["endpoints"] == [{"path": "/health", "method": "GET"}]
    assert seen["headers"] == {"Authorization": "Bearer x"}
