"""Analyzer extracted from dast_analyzer (mechanical split; see dast/base.py)."""

from typing import Dict, List, Optional

from framework.security.dast.active import ActiveAPIScanner, ActiveScanConfig
from framework.security.dast.base import (
    DASTTestType,
    DASTSeverity,
    DASTFinding,
)


class APISecurityTester:
    """API Security Tester.

    By default (no :class:`ActiveScanConfig` with ``active=True``) this is passive: it issues no
    requests and reports one honest INFO finding so a report distinguishes "not tested" from
    "no vulnerabilities found". With an authorized active config it delegates to
    :class:`~framework.security.dast.active.ActiveAPIScanner`, which does the real probing.
    """

    def __init__(self, config: Optional[ActiveScanConfig] = None) -> None:
        self._config = config or ActiveScanConfig()
        # Build the scanner once per tester so its rate limiter spans the whole scan. The
        # authorization gate lives in ActiveAPIScanner.__init__, so an active-but-unauthorized
        # config raises here rather than silently running.
        self._scanner: Optional[ActiveAPIScanner] = (
            ActiveAPIScanner(
                authorized=self._config.authorized,
                rate_limit_rps=self._config.rate_limit_rps,
                transport=self._config.transport,
            )
            if self._config.active
            else None
        )

    def test_endpoint(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
    ) -> List[DASTFinding]:
        """Test an API endpoint for vulnerabilities.

        Active mode (an authorized :class:`ActiveScanConfig`) runs the real injection / auth /
        rate-limit / CORS probes. Otherwise this returns one explicit INFO finding — never an
        empty list, which a caller would read as "endpoint is secure".
        """
        if self._scanner is not None:
            return self._scanner.scan_endpoint(url, method, headers, params)
        return [
            DASTFinding(
                test_type=DASTTestType.API,
                severity=DASTSeverity.INFO,
                title="Active API security testing not performed",
                description=(
                    "Active endpoint testing (SQL injection, XSS, path traversal, "
                    "auth bypass, rate limiting, CORS) was not run, so this endpoint "
                    "was NOT assessed for those issues. Pass an authorized active "
                    "config (CLI: --active with authorization) to enable it."
                ),
                evidence=f"{method} {url}",
                recommendation=(
                    "Re-run with active scanning enabled against a target you are "
                    "authorized to test, or treat this result as 'not tested' rather "
                    "than 'secure'."
                ),
            )
        ]
