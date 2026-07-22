"""Analyzer extracted from dast_analyzer (mechanical split; see dast/base.py)."""

from typing import Dict, List, Optional

from framework.security.dast.base import (
    DASTTestType,
    DASTSeverity,
    DASTFinding,
)


class APISecurityTester:
    """
    API Security Tester

    Tests API endpoints for common vulnerabilities.
    """

    # Common injection payloads
    SQL_PAYLOADS = [
        "' OR '1'='1",
        "1; DROP TABLE users--",
        "1' AND '1'='1",
        "admin'--",
        "' UNION SELECT NULL--",
    ]

    XSS_PAYLOADS = [
        "<script>alert('XSS')</script>",
        "'\"><img src=x onerror=alert('XSS')>",
        "javascript:alert('XSS')",
        "<svg onload=alert('XSS')>",
    ]

    NOSQL_PAYLOADS = [
        '{"$gt": ""}',
        '{"$ne": null}',
        '{"$where": "sleep(5000)"}',
    ]

    PATH_TRAVERSAL_PAYLOADS = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "....//....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ]

    def test_endpoint(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
    ) -> List[DASTFinding]:
        """Test an API endpoint for vulnerabilities.

        Active injection testing (SQL/XSS/path-traversal/auth/rate-limit/CORS)
        is not yet implemented: it requires issuing real HTTP requests against
        the target. Rather than return an empty list — which a caller would read
        as "endpoint is secure" — surface one explicit INFO finding so the
        report distinguishes "not tested" from "no vulnerabilities found".
        """
        return [
            DASTFinding(
                test_type=DASTTestType.API,
                severity=DASTSeverity.INFO,
                title="Active API security testing not performed",
                description=(
                    "Active endpoint testing (SQL injection, XSS, path traversal, "
                    "auth bypass, rate limiting, CORS) is not implemented in this "
                    "build, so this endpoint was NOT assessed for those issues."
                ),
                evidence=f"{method} {url}",
                recommendation=(
                    "Run a dedicated DAST tool against this endpoint, or treat "
                    "this result as 'not tested' rather than 'secure'."
                ),
            )
        ]

    # Active injection-test stubs were removed: they looped over payload lists
    # but never issued a request, so they always returned [] (a false "secure").
    # test_endpoint() now reports an explicit "not tested" finding instead.
