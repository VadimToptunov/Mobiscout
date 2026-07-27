"""Behaviour tests for the DASTAnalyzer orchestration layer.

DASTAnalyzer combines four sub-analyzers. These tests drive the parts that run
fully in-process — captured-traffic analysis and API endpoint testing — with
in-memory fixtures and assert the real findings produced (titles, severities,
CWE ids). SSL/TLS paths that require a live host are driven against a reserved
``.invalid`` hostname (guaranteed to fail DNS offline, deterministically) or
have the network sub-analyzer stubbed, so no test depends on external hosts.
The summary/report/HTML exporters are asserted on their concrete output.
"""

import json
from datetime import datetime

import pytest

from framework.security.dast.base import (
    DASTTestType,
    DASTSeverity,
    NetworkRequest,
    DASTFinding,
    DASTResult,
    SSLAnalysisResult,
    APITestResult,
)
from framework.security.dast.analyzer import DASTAnalyzer

ALL_SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'",
    "X-XSS-Protection": "1; mode=block",
}


@pytest.fixture()
def analyzer():
    return DASTAnalyzer()


def _titles(findings):
    return {f.title for f in findings}


# --------------------------------------------------------------------------- #
# analyze_traffic -> NetworkTrafficAnalyzer real findings
# --------------------------------------------------------------------------- #
class TestAnalyzeTraffic:
    def test_cleartext_http_request_flagged_high(self, analyzer):
        request = NetworkRequest(
            timestamp=datetime.now(),
            method="POST",
            url="http://api.example.com/login",
            headers={},  # no security headers present
            body=None,
            is_secure=False,
        )

        findings = analyzer.analyze_traffic([request])

        cleartext = [f for f in findings if f.title == "Cleartext HTTP traffic"]
        assert len(cleartext) == 1
        assert cleartext[0].severity is DASTSeverity.HIGH
        assert cleartext[0].cwe_id == "CWE-319"
        # All five required security headers are reported missing.
        missing = [f for f in findings if f.title.startswith("Missing security header")]
        assert len(missing) == 5

    def test_secure_request_with_all_headers_is_clean(self, analyzer):
        request = NetworkRequest(
            timestamp=datetime.now(),
            method="POST",
            url="https://api.example.com/ok",
            headers=dict(ALL_SECURITY_HEADERS),
            body='{"status":"ok"}',
            is_secure=True,
            response_body="ok",
        )

        assert analyzer.analyze_traffic([request]) == []

    def test_sensitive_data_in_url_and_body_flagged(self, analyzer):
        request = NetworkRequest(
            timestamp=datetime.now(),
            method="GET",
            url="https://api.example.com/reset?token=abcdef123456",
            headers=dict(ALL_SECURITY_HEADERS),
            body="please contact user@example.com",
            is_secure=True,
        )

        findings = analyzer.analyze_traffic([request])
        titles = _titles(findings)

        assert "Sensitive data in URL" in titles  # 'token' query param
        assert "Potential email in request" in titles  # email pattern in body
        # No missing-header noise because all headers are present.
        assert not any(t.startswith("Missing security header") for t in titles)

    def test_jwt_in_response_body_flagged_high(self, analyzer):
        jwt = "eyJhbGciOi.eyJzdWIiOiIx.SflKxwRJSMeKKF2QT4"
        request = NetworkRequest(
            timestamp=datetime.now(),
            method="GET",
            url="https://api.example.com/me",
            headers=dict(ALL_SECURITY_HEADERS),
            body=None,
            is_secure=True,
            response_body=f'{{"token":"{jwt}"}}',
        )

        findings = analyzer.analyze_traffic([request])
        jwt_findings = [f for f in findings if "jwt" in f.title.lower()]

        assert len(jwt_findings) == 1
        assert jwt_findings[0].severity is DASTSeverity.HIGH
        assert jwt_findings[0].cwe_id == "CWE-200"


# --------------------------------------------------------------------------- #
# analyze_api / test_api -> APISecurityTester "not tested" finding
# --------------------------------------------------------------------------- #
class TestApiAnalysis:
    def test_analyze_api_reports_not_tested_per_endpoint(self, analyzer):
        endpoints = [{"path": "/users", "method": "GET"}, {"path": "/login", "method": "POST"}]

        findings = analyzer.analyze_api("https://api.example.com", endpoints)

        # One explicit INFO "not tested" finding per endpoint (never a false
        # "secure" empty result).
        assert len(findings) == 2
        assert all(f.severity is DASTSeverity.INFO for f in findings)
        assert all(f.test_type is DASTTestType.API for f in findings)

    def test_test_api_annotates_endpoint_and_method(self, analyzer):
        result = analyzer.test_api(
            "https://api.example.com/",
            headers={"Authorization": "Bearer x"},
            endpoints=[{"path": "/orders", "method": "DELETE"}],
        )

        assert isinstance(result, APITestResult)
        assert result.endpoints_tested == 1
        assert result.base_url == "https://api.example.com/"
        finding = result.findings[0]
        assert finding.endpoint == "/orders"
        assert finding.method == "DELETE"

    def test_test_api_defaults_to_root_endpoint(self, analyzer):
        result = analyzer.test_api("https://api.example.com")

        assert result.endpoints_tested == 1
        assert result.findings[0].endpoint == "/"


# --------------------------------------------------------------------------- #
# Summary / report / HTML
# --------------------------------------------------------------------------- #
class TestSummaryAndExports:
    def _sample_findings(self):
        return [
            DASTFinding(
                test_type=DASTTestType.SSL_TLS,
                severity=DASTSeverity.CRITICAL,
                title="Expired SSL certificate",
                description="cert expired",
                evidence="notAfter",
                recommendation="renew",
                cwe_id="CWE-298",
            ),
            DASTFinding(
                test_type=DASTTestType.NETWORK,
                severity=DASTSeverity.HIGH,
                title="Cleartext HTTP traffic",
                description="http",
                evidence="http://x",
                recommendation="use https",
            ),
            DASTFinding(
                test_type=DASTTestType.NETWORK,
                severity=DASTSeverity.MEDIUM,
                title="Missing security header: CSP",
                description="no csp",
                evidence="absent",
                recommendation="add csp",
            ),
        ]

    def test_get_summary_counts(self, analyzer):
        summary = analyzer.get_summary(self._sample_findings())

        assert summary["total_findings"] == 3
        assert summary["critical"] == 1
        assert summary["high"] == 1
        assert summary["medium"] == 1
        assert summary["by_type"]["network"] == 2
        assert summary["by_type"]["ssl_tls"] == 1

    def test_export_report_writes_json(self, analyzer, tmp_path):
        out = tmp_path / "nested" / "dast.json"

        analyzer.export_report(self._sample_findings(), out)

        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["total_findings"] == 3
        assert len(data["findings"]) == 3
        assert data["findings"][0]["title"] == "Expired SSL certificate"

    def test_export_html_contains_target_and_findings(self, analyzer, tmp_path):
        result = DASTResult(findings=self._sample_findings(), target="example.com", port=443)
        out = tmp_path / "dast.html"

        analyzer.export_html(result, out)

        content = out.read_text(encoding="utf-8")
        assert "example.com" in content
        assert "Expired SSL certificate" in content
        assert "Cleartext HTTP traffic" in content


# --------------------------------------------------------------------------- #
# SSL/TLS entry points — the live-host I/O is stubbed so no test touches DNS.
# DASTAnalyzer's own orchestration (delegation, result wrapping, the
# connection-failure fallback) is what is exercised here.
# --------------------------------------------------------------------------- #
class TestSSLEntryPoints:
    def test_analyze_host_delegates_to_ssl_analyzer(self, analyzer):
        sentinel = [
            DASTFinding(
                test_type=DASTTestType.SSL_TLS,
                severity=DASTSeverity.HIGH,
                title="Self-signed certificate",
                description="d",
                evidence="e",
                recommendation="r",
            )
        ]
        analyzer.ssl_analyzer.analyze_host = lambda hostname, port: sentinel

        findings = analyzer.analyze_host("example.com", 8443)

        assert findings is sentinel

    def test_analyze_wraps_ssl_findings_in_dast_result(self, analyzer):
        # Stub the live SSL scan; analyze() must forward its findings and stamp
        # target/port onto a well-formed DASTResult.
        finding = DASTFinding(
            test_type=DASTTestType.SSL_TLS,
            severity=DASTSeverity.MEDIUM,
            title="Deprecated protocol supported: TLSv1.0",
            description="d",
            evidence="e",
            recommendation="r",
        )
        analyzer.ssl_analyzer.analyze_host = lambda hostname, port: [finding]

        result = analyzer.analyze("example.com", port=8443)

        assert isinstance(result, DASTResult)
        assert result.target == "example.com"
        assert result.port == 8443
        assert result.findings == [finding]

    def test_analyze_ssl_returns_empty_details_on_connection_failure(self, analyzer, monkeypatch):
        import framework.security.dast.analyzer as analyzer_mod

        # No live connection: SSL scan yields nothing and the detail probe fails.
        analyzer.ssl_analyzer.analyze_host = lambda hostname, port: []

        def _boom(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(analyzer_mod.socket, "create_connection", _boom)

        result = analyzer.analyze_ssl("example.com", port=443)

        assert isinstance(result, SSLAnalysisResult)
        # Connection failed, so no protocol/cipher/expiry could be read.
        assert result.protocol == ""
        assert result.cipher_suite == ""
        assert result.cert_expiry == ""
        assert result.findings == []
