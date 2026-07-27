"""Regression guards for confirmed security-subsystem correctness bugs.

Each test fails against the pre-fix code and passes after. Bugs covered:

1. Insecure-RNG regex flagged SecureRandom()/MockRandom() (false positive).
2. Phone PII regex matched any bare integer like "12345" (false positive).
3. Secret false-positive filter substring-matched "test" inside "latest"
   and dropped real secrets (false negative).
4. arc4random wrongly flagged as insecure RNG; "SHA-1"/"SHA_1" missed.
5. Certificate-pinning analyzer aborted on a single unreadable file.
6. Taint findings hardcoded HIGH/CWE-20; insecure-API entries mislabeled
   every non-WebView API as command injection.
"""

import tempfile
from pathlib import Path

from framework.security.advanced.secure_coding import SecureCodingAnalyzer
from framework.security.advanced.privacy import PrivacyComplianceChecker
from framework.security.advanced.secrets import HardcodedSecretsScanner
from framework.security.advanced.pinning import CertificatePinningAnalyzer
from framework.security.sast.crypto import CryptoAnalyzer
from framework.security.sast.insecure_api import InsecureAPIAnalyzer
from framework.security.sast.analyzer import SASTAnalyzer
from framework.security.sast.base import VulnerabilityType, Severity


# ---------------------------------------------------------------------------
# Bug 1 - insecure RNG word boundary
# ---------------------------------------------------------------------------
class TestInsecureRandomBoundary:
    def _titles(self, source: str, tmp_path: Path):
        f = tmp_path / "Sample.java"
        f.write_text(source, encoding="utf-8")
        return [v.title for v in SecureCodingAnalyzer().analyze(tmp_path)]

    def test_secure_random_not_flagged(self, tmp_path):
        titles = self._titles("SecureRandom r = new SecureRandom();\n", tmp_path)
        assert "Insecure Random Number Generator" not in titles

    def test_mock_random_not_flagged(self, tmp_path):
        titles = self._titles("Random r = new MockRandom();\n", tmp_path)
        assert "Insecure Random Number Generator" not in titles

    def test_new_random_flagged(self, tmp_path):
        titles = self._titles("Random r = new Random();\n", tmp_path)
        assert "Insecure Random Number Generator" in titles


# ---------------------------------------------------------------------------
# Bug 2 - phone PII regex requires real formatting
# ---------------------------------------------------------------------------
class TestPhonePIIRegex:
    def _phone_findings(self, logged_value: str, tmp_path: Path):
        src = tmp_path / "A.java"
        src.write_text(f'Log.d("TAG", "{logged_value}");\n', encoding="utf-8")
        vulns = PrivacyComplianceChecker().check_pii_logging(tmp_path)
        return [v for v in vulns if "phone" in v.title.lower()]

    def test_bare_integer_not_flagged(self, tmp_path):
        assert self._phone_findings("12345", tmp_path) == []

    def test_real_phone_flagged(self, tmp_path):
        assert self._phone_findings("+1-415-555-2671", tmp_path)

    def test_regex_directly(self):
        pat = PrivacyComplianceChecker().pii_patterns["phone"]
        assert pat.search("12345") is None
        assert pat.search("+1-415-555-2671") is not None


# ---------------------------------------------------------------------------
# Bug 3 - secret filter must not drop secrets next to "latest"/"manifest"
# ---------------------------------------------------------------------------
class TestSecretFalsePositiveWordBoundary:
    def test_secret_adjacent_to_latest_reported(self):
        scanner = HardcodedSecretsScanner()
        content = 'latest_api_key = "aB3xYz9KpQ7mN2wL8vR4tE6sD0fG1hJ5"'
        vulns = scanner.scan_content(content, "config.py")
        assert any("api key" in v.title.lower() for v in vulns)

    def test_secret_near_manifest_reported(self):
        scanner = HardcodedSecretsScanner()
        content = '# manifest\napi_key = "aB3xYz9KpQ7mN2wL8vR4tE6sD0fG1hJ5"'
        vulns = scanner.scan_content(content, "config.py")
        assert any("api key" in v.title.lower() for v in vulns)

    def test_genuine_test_placeholder_still_filtered(self):
        scanner = HardcodedSecretsScanner()
        # A standalone "test" token adjacent to the value is still a FP.
        assert scanner.is_false_positive('api_key = "value"', "this is a test fixture")
        # But "latest" must NOT be treated as the word "test".
        assert not scanner.is_false_positive("secretvalue", "the latest greatest manifest")


# ---------------------------------------------------------------------------
# Bug 4 - arc4random not insecure; SHA-1 / SHA_1 detected
# ---------------------------------------------------------------------------
class TestCryptoRandomAndSha1:
    def _findings(self, source: str, suffix: str = ".swift"):
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
            f.write(source)
            path = Path(f.name)
        try:
            return CryptoAnalyzer().analyze(path)
        finally:
            path.unlink()

    def test_arc4random_not_flagged(self):
        findings = self._findings("let n = arc4random_uniform(100)\n")
        assert not any(f.vulnerability_type == VulnerabilityType.INSECURE_RANDOM for f in findings)

    def test_sha1_dashed_flagged(self):
        findings = self._findings('let d = MessageDigest.getInstance("SHA-1")\n', suffix=".java")
        assert any("SHA1" in f.title for f in findings)

    def test_sha1_underscore_flagged(self):
        findings = self._findings('digest = hashes.Hash("SHA_1")\n', suffix=".py")
        assert any("SHA1" in f.title for f in findings)


# ---------------------------------------------------------------------------
# Bug 5 - pinning analyzer survives an unreadable file
# ---------------------------------------------------------------------------
class TestPinningUnreadableFile:
    def test_unreadable_file_does_not_abort(self, tmp_path):
        # A directory named like a source file makes read_text raise
        # IsADirectoryError (an OSError) deterministically, independent of the
        # running user's privileges.
        (tmp_path / "evil.java").mkdir()
        good = tmp_path / "good.java"
        good.write_text("SSLContext c = trustAllCerts();\n", encoding="utf-8")

        vulns = CertificatePinningAnalyzer().analyze_android(tmp_path)

        # The readable file was still analyzed past the unreadable one.
        assert any("Bypass" in v.title for v in vulns)

    def test_unreadable_network_config_does_not_abort(self, tmp_path):
        res_xml = tmp_path / "res" / "xml"
        res_xml.mkdir(parents=True)
        # network_security_config.xml as a directory -> read raises OSError.
        (res_xml / "network_security_config.xml").mkdir()
        # Should not raise.
        CertificatePinningAnalyzer().analyze_android(tmp_path)


# ---------------------------------------------------------------------------
# Bug 6 - correct severity/CWE/type in taint and insecure-API findings
# ---------------------------------------------------------------------------
class TestSastSeverityCweMapping:
    def test_sqli_taint_reports_cwe_89(self, tmp_path):
        src = tmp_path / "app.py"
        src.write_text("user = input()\ncursor.execute(user)\n", encoding="utf-8")
        findings = SASTAnalyzer().analyze_file(src)
        taint = [f for f in findings if f.taint_flow is not None]
        sqli = [f for f in taint if f.vulnerability_type == VulnerabilityType.SQL_INJECTION]
        assert sqli, "expected a SQL-injection taint flow"
        assert sqli[0].cwe_id == "CWE-89"
        assert sqli[0].severity == Severity.HIGH

    def test_command_injection_taint_reports_cwe_78(self, tmp_path):
        src = tmp_path / "app.py"
        src.write_text("user = input()\nos.system(user)\n", encoding="utf-8")
        findings = SASTAnalyzer().analyze_file(src)
        cmd = [
            f
            for f in findings
            if f.taint_flow is not None and f.vulnerability_type == VulnerabilityType.COMMAND_INJECTION
        ]
        assert cmd, "expected a command-injection taint flow"
        assert cmd[0].cwe_id == "CWE-78"

    def test_trustmanager_not_command_injection(self, tmp_path):
        src = tmp_path / "Net.java"
        src.write_text("class Insecure implements X509TrustManager {}\n", encoding="utf-8")
        findings = InsecureAPIAnalyzer().analyze(src)
        tm = [f for f in findings if "TrustManager" in f.title]
        assert tm, "expected a TrustManager finding"
        for f in tm:
            assert f.vulnerability_type != VulnerabilityType.COMMAND_INJECTION
            assert f.vulnerability_type == VulnerabilityType.IMPROPER_CERT_VALIDATION
            assert f.cwe_id == "CWE-295"

    def test_insecure_api_severity_preserved(self, tmp_path):
        # eval() keeps its API-specific CRITICAL severity and CWE-95.
        src = tmp_path / "app.py"
        src.write_text("x = eval(data)\n", encoding="utf-8")
        findings = InsecureAPIAnalyzer().analyze(src)
        ev = [f for f in findings if f.title.startswith("Insecure API usage: eval")]
        assert ev
        assert ev[0].severity == Severity.CRITICAL
        assert ev[0].cwe_id == "CWE-95"
