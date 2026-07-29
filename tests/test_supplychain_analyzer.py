"""Behaviour tests for the SupplyChainAnalyzer vulnerability/advisory logic.

These drive the analyzer's real decision logic against parsed dependency sets
and real fixture manifests written into ``tmp_path``:

- ``_version_matches`` implements the advisory version-range comparison. It must
  read two-char operators (<=, >=, ==) correctly and compare versions
  numerically, not lexically (so 2.0 < 2.10). These are the exact bugs the
  method's docstring calls out, so they are asserted directly.
- ``_check_python/js/gradle_vulnerabilities`` map a vulnerable dependency to a
  ``SupplyChainFinding`` carrying the right CVE and severity.
- ``_check_licenses`` flags copyleft runtime dependencies only.
- ``analyze`` / ``scan_directory`` glue parsing to the CLI-facing result.
- SBOM, summary and report exporters produce the documented shapes.
"""

import json
import sys

import pytest

from framework.security.supplychain.base import (
    DependencyType,
    LicenseType,
    VulnerabilitySeverity,
    Dependency,
    SupplyChainResult,
    DependencyWithVulns,
)
from framework.security.supplychain.analyzer import SupplyChainAnalyzer


@pytest.fixture()
def analyzer():
    return SupplyChainAnalyzer()


# --------------------------------------------------------------------------- #
# _version_matches — the advisory range comparison
# --------------------------------------------------------------------------- #
class TestVersionMatches:
    """Version specs must parse two-char operators and compare numerically."""

    @pytest.mark.parametrize(
        "current,spec,expected",
        [
            ("5.3.1", "< 5.4", True),  # below fixed version -> vulnerable
            ("5.4", "< 5.4", False),  # boundary is exclusive
            ("5.4", "<= 5.4", True),  # two-char operator honoured
            ("6.0", "<= 5.4", False),
            ("2.9", ">= 2.8", True),
            ("2.7", ">= 2.8", False),
            ("1.0", "> 0.9", True),
            ("1.0", "== 1.0", True),
            ("1.1", "== 1.0", False),
        ],
    )
    def test_operator_comparisons(self, analyzer, current, spec, expected):
        assert analyzer._version_matches(current, spec) is expected

    def test_numeric_not_lexical_ordering(self, analyzer):
        # The old bug compared lexically, making "2.0" < "2.10" evaluate False.
        assert analyzer._version_matches("2.0", "<= 2.10") is True
        assert analyzer._version_matches("2.10", "< 2.9") is False

    def test_no_operator_is_exact_match(self, analyzer):
        assert analyzer._version_matches("1.2.3", "1.2.3") is True
        assert analyzer._version_matches("1.2.4", "1.2.3") is False

    def test_unparseable_version_is_conservative_no_match(self, analyzer):
        # packaging raises InvalidVersion -> caught -> no match (not a crash).
        assert analyzer._version_matches("not-a-version", "< 5.4") is False

    def test_numeric_fallback_when_packaging_missing(self, analyzer, monkeypatch):
        # Force the ImportError branch: the tuple fallback must still order
        # 2.0 below 2.10 (never lexically).
        monkeypatch.setitem(sys.modules, "packaging.version", None)
        assert analyzer._version_matches("2.0", "<= 2.10") is True
        assert analyzer._version_matches("2.10", "<= 2.0") is False


# --------------------------------------------------------------------------- #
# Vulnerability detection over a parsed dependency set
# --------------------------------------------------------------------------- #
class TestVulnerabilityChecks:
    def test_python_vulnerable_dependency_flagged_with_cve(self, analyzer):
        deps = [
            Dependency(name="pyyaml", version="5.3.1", dep_type=DependencyType.PYTHON),
            Dependency(name="flask", version="2.0.0", dep_type=DependencyType.PYTHON),
        ]
        findings = analyzer._check_python_vulnerabilities(deps)

        # pyyaml 5.3.1 < 5.4 -> vulnerable; flask 2.0.0 is NOT < 2.0.0 -> clean.
        assert len(findings) == 1
        finding = findings[0]
        assert finding.finding_type == "vulnerability"
        assert finding.dependency.name == "pyyaml"
        assert finding.severity is VulnerabilitySeverity.CRITICAL
        assert finding.vulnerability.cve_id == "CVE-2020-14343"
        assert "pyyaml" in finding.recommendation

    def test_python_unknown_and_patched_packages_not_flagged(self, analyzer):
        deps = [
            Dependency(name="some-internal-lib", version="1.0", dep_type=DependencyType.PYTHON),
            Dependency(name="pyyaml", version="6.0", dep_type=DependencyType.PYTHON),  # patched
        ]
        assert analyzer._check_python_vulnerabilities(deps) == []

    def test_js_vulnerable_dependency_flagged(self, analyzer):
        deps = [Dependency(name="lodash", version="4.17.20", dep_type=DependencyType.JAVASCRIPT)]
        findings = analyzer._check_js_vulnerabilities(deps)

        assert len(findings) == 1
        assert findings[0].vulnerability.cve_id == "CVE-2021-23337"
        assert findings[0].severity is VulnerabilitySeverity.HIGH

    def test_gradle_log4shell_flagged_as_critical(self, analyzer):
        deps = [
            Dependency(
                name="org.apache.logging.log4j:log4j-core",
                version="2.14.0",
                dep_type=DependencyType.GRADLE,
            )
        ]
        findings = analyzer._check_gradle_vulnerabilities(deps)

        assert len(findings) == 1
        assert findings[0].vulnerability.cve_id == "CVE-2021-44228"
        assert findings[0].severity is VulnerabilitySeverity.CRITICAL

    def test_cocoapods_vulnerable_dependency_flagged(self, analyzer):
        # CocoaPods deps were parsed but never vuln-checked before this change.
        deps = [
            Dependency(name="libwebp", version="1.3.1", dep_type=DependencyType.COCOAPODS),
            Dependency(name="Alamofire", version="5.4.3", dep_type=DependencyType.COCOAPODS),  # clean
        ]
        findings = analyzer._check_cocoapods_vulnerabilities(deps)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.dependency.name == "libwebp"
        assert finding.vulnerability.cve_id == "CVE-2023-4863"
        assert finding.severity is VulnerabilitySeverity.CRITICAL

    def test_all_ecosystem_checks_share_one_implementation(self, analyzer):
        # The four public checks route through the single _check helper; a
        # standalone table exercised through it must flag on version match.
        table = {"widget": [("< 2.0", "CVE-0000-0001", VulnerabilitySeverity.HIGH, "demo")]}
        deps = [Dependency(name="widget", version="1.5", dep_type=DependencyType.PYTHON)]
        findings = analyzer._check(deps, table)
        assert len(findings) == 1
        assert findings[0].vulnerability.cve_id == "CVE-0000-0001"


# --------------------------------------------------------------------------- #
# License compliance
# --------------------------------------------------------------------------- #
class TestLicenseChecks:
    def test_copyleft_runtime_dependency_flagged(self, analyzer):
        deps = [
            Dependency(
                name="gpl-lib",
                version="1.0",
                dep_type=DependencyType.PYTHON,
                license="GPL-3.0",
                license_type=LicenseType.COPYLEFT,
            )
        ]
        findings = analyzer._check_licenses(deps)

        assert len(findings) == 1
        assert findings[0].finding_type == "license"
        assert findings[0].severity is VulnerabilitySeverity.MEDIUM
        assert findings[0].dependency.name == "gpl-lib"

    def test_copyleft_dev_dependency_and_permissive_not_flagged(self, analyzer):
        deps = [
            Dependency(
                name="gpl-tool",
                version="1.0",
                dep_type=DependencyType.PYTHON,
                license_type=LicenseType.COPYLEFT,
                dev_dependency=True,  # dev-only copyleft -> no distribution risk
            ),
            Dependency(
                name="mit-lib",
                version="1.0",
                dep_type=DependencyType.PYTHON,
                license_type=LicenseType.PERMISSIVE,
            ),
        ]
        assert analyzer._check_licenses(deps) == []


# --------------------------------------------------------------------------- #
# scan_directory / analyze — end to end over real manifests
# --------------------------------------------------------------------------- #
class TestScanAndAnalyze:
    def test_scan_directory_parses_and_flags(self, analyzer, tmp_path):
        (tmp_path / "requirements.txt").write_text("pyyaml==5.3.1\nflask==2.1.0\n", encoding="utf-8")

        dependencies, findings = analyzer.scan_directory(tmp_path)

        names = {d.name for d in dependencies}
        assert {"pyyaml", "flask"} <= names
        vuln_findings = [f for f in findings if f.finding_type == "vulnerability"]
        assert any(f.dependency.name == "pyyaml" for f in vuln_findings)

    def test_scan_directory_covers_all_ecosystems(self, analyzer, tmp_path):
        # One manifest per supported ecosystem -> every parser branch of
        # scan_directory runs and its deps land in the combined catalogue.
        (tmp_path / "requirements.txt").write_text("flask==2.1.0\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\ndependencies=['click']\n", encoding="utf-8")
        (tmp_path / "package.json").write_text('{"dependencies":{"axios":"1.0.0"}}', encoding="utf-8")
        (tmp_path / "build.gradle").write_text(
            'dependencies {\n  implementation "com.google.code.gson:gson:2.8.9"\n}\n',
            encoding="utf-8",
        )
        (tmp_path / "Podfile.lock").write_text("PODS:\n  - Alamofire (5.4.3)\n", encoding="utf-8")

        dependencies, _ = analyzer.scan_directory(tmp_path)
        names = {d.name for d in dependencies}

        assert {"flask", "click", "axios", "com.google.code.gson:gson", "Alamofire"} <= names
        ecosystems = {d.dep_type for d in dependencies}
        assert {
            DependencyType.PYTHON,
            DependencyType.JAVASCRIPT,
            DependencyType.GRADLE,
            DependencyType.COCOAPODS,
        } <= ecosystems

    def test_scan_directory_flags_vulnerable_cocoapod(self, analyzer, tmp_path):
        # A Podfile.lock pinning a vulnerable pod now surfaces a vuln finding.
        (tmp_path / "Podfile.lock").write_text("PODS:\n  - libwebp (1.3.1)\n", encoding="utf-8")

        dependencies, findings = analyzer.scan_directory(tmp_path)

        assert any(d.name == "libwebp" for d in dependencies)
        vuln = [f for f in findings if f.finding_type == "vulnerability" and f.dependency.name == "libwebp"]
        assert len(vuln) == 1
        assert vuln[0].vulnerability.cve_id == "CVE-2023-4863"

    def test_scan_directory_skips_node_modules_package_json(self, analyzer, tmp_path):
        # Vendored deps under node_modules must not be treated as project deps.
        nm = tmp_path / "node_modules" / "left-pad"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text('{"dependencies":{"sneaky":"1.0.0"}}', encoding="utf-8")

        dependencies, _ = analyzer.scan_directory(tmp_path)

        assert all(d.name != "sneaky" for d in dependencies)

    def test_analyze_returns_cli_result_with_vulnerability(self, analyzer, tmp_path):
        (tmp_path / "requirements.txt").write_text("pyyaml==5.3.1\n", encoding="utf-8")

        result = analyzer.analyze(tmp_path)

        assert isinstance(result, SupplyChainResult)
        assert any(d.name == "pyyaml" for d in result.dependencies)
        assert len(result.vulnerabilities) == 1
        vuln = result.vulnerabilities[0]
        assert vuln.package_name == "pyyaml"
        assert vuln.installed_version == "5.3.1"
        assert vuln.cve_id == "CVE-2020-14343"
        assert vuln.severity == "critical"

    def test_analyze_can_skip_vulnerability_reporting(self, analyzer, tmp_path):
        (tmp_path / "requirements.txt").write_text("pyyaml==5.3.1\n", encoding="utf-8")

        result = analyzer.analyze(tmp_path, check_vulnerabilities=False)

        # Dependencies are still catalogued, but no vuln findings surface.
        assert any(d.name == "pyyaml" for d in result.dependencies)
        assert result.vulnerabilities == []

    def test_analyze_deduplicates_dependencies_by_name_version(self, analyzer, tmp_path):
        # Two requirements files pinning the same package -> one catalogued entry.
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n", encoding="utf-8")
        (tmp_path / "requirements-dev.txt").write_text("requests==2.28.0\n", encoding="utf-8")

        result = analyzer.analyze(tmp_path)

        requests_entries = [d for d in result.dependencies if d.name == "requests"]
        assert len(requests_entries) == 1


# --------------------------------------------------------------------------- #
# SBOM / summary / reports
# --------------------------------------------------------------------------- #
class TestArtifacts:
    def test_generate_sbom_shape_and_purls(self, analyzer):
        deps = [
            Dependency(name="flask", version="2.0.0", dep_type=DependencyType.PYTHON),
            Dependency(name="lodash", version="4.17.21", dep_type=DependencyType.JAVASCRIPT),
        ]
        sbom = analyzer.generate_sbom(deps)

        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.4"
        purls = {c["purl"] for c in sbom["components"]}
        assert "pkg:python/flask@2.0.0" in purls
        assert "pkg:javascript/lodash@4.17.21" in purls

    def test_get_summary_counts_by_severity_and_type(self, analyzer):
        deps = [
            Dependency(name="pyyaml", version="5.3.1", dep_type=DependencyType.PYTHON),  # critical vuln
            Dependency(
                name="gpl-lib",
                version="1.0",
                dep_type=DependencyType.PYTHON,
                license_type=LicenseType.COPYLEFT,
            ),  # medium license
        ]
        findings = analyzer._check_python_vulnerabilities(deps) + analyzer._check_licenses(deps)

        summary = analyzer.get_summary(findings)

        assert summary["total_findings"] == 2
        assert summary["critical"] == 1
        assert summary["medium"] == 1
        assert summary["by_type"]["vulnerability"] == 1
        assert summary["by_type"]["license"] == 1

    def test_export_report_writes_json(self, analyzer, tmp_path):
        deps = [Dependency(name="pyyaml", version="5.3.1", dep_type=DependencyType.PYTHON)]
        findings = analyzer._check_python_vulnerabilities(deps)
        out = tmp_path / "reports" / "supply.json"

        analyzer.export_report(deps, findings, out)

        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["total_findings"] == 1
        assert data["dependencies"][0]["name"] == "pyyaml"
        assert data["sbom"]["bomFormat"] == "CycloneDX"

    def test_generate_sbom_file_cyclonedx(self, analyzer, tmp_path):
        result = SupplyChainResult(
            dependencies=[DependencyWithVulns(name="flask", version="2.0.0", ecosystem="python")]
        )
        out = tmp_path / "sbom.json"

        analyzer.generate_sbom_file(result, out, format="cyclonedx")

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["bomFormat"] == "CycloneDX"
        assert data["components"][0]["name"] == "flask"

    def test_generate_sbom_file_spdx(self, analyzer, tmp_path):
        result = SupplyChainResult(
            dependencies=[DependencyWithVulns(name="flask", version="2.0.0", ecosystem="python")]
        )
        out = tmp_path / "sbom-spdx.json"

        analyzer.generate_sbom_file(result, out, format="spdx")

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["spdxVersion"] == "SPDX-2.3"
        assert data["packages"][0]["name"] == "flask"
        assert data["packages"][0]["versionInfo"] == "2.0.0"

    def test_generate_sbom_file_unknown_ecosystem_defaults_to_python(self, analyzer, tmp_path):
        # ecosystem "pypi" is not a DependencyType value -> falls back to python.
        result = SupplyChainResult(dependencies=[DependencyWithVulns(name="flask", version="2.0.0", ecosystem="pypi")])
        out = tmp_path / "sbom-fallback.json"

        analyzer.generate_sbom_file(result, out, format="cyclonedx")

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["components"][0]["purl"] == "pkg:python/flask@2.0.0"

    def test_export_html_contains_vulnerable_package(self, analyzer, tmp_path):
        result = analyzer.analyze(self._project_with_pyyaml(tmp_path))
        out = tmp_path / "report.html"

        analyzer.export_html(result, out)

        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "Supply Chain Security Report" in content
        assert "pyyaml" in content
        assert "CVE-2020-14343" in content

    @staticmethod
    def _project_with_pyyaml(tmp_path):
        (tmp_path / "requirements.txt").write_text("pyyaml==5.3.1\n", encoding="utf-8")
        return tmp_path
