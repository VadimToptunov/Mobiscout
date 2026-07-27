"""Behaviour tests for the supply-chain dependency parsers.

Each parser turns a real manifest file (requirements.txt, pyproject.toml,
package.json, build.gradle, Podfile.lock) into a list of ``Dependency``
objects. These tests feed real fixture files written into ``tmp_path`` and
assert the parsed dependency set: names (normalised), versions (operator
prefixes stripped), ecosystem type, and the dev-dependency flag. They also
guard the failure modes the parsers must swallow silently — an unreadable or
malformed manifest drops its deps from the scan rather than aborting it.
"""

import sys

from framework.security.supplychain.base import DependencyType
from framework.security.supplychain.parsers import (
    PythonDependencyParser,
    JavaScriptDependencyParser,
    GradleDependencyParser,
    CocoaPodsDependencyParser,
)


def _by_name(deps):
    return {d.name: d for d in deps}


# --------------------------------------------------------------------------- #
# PythonDependencyParser.parse_requirements
# --------------------------------------------------------------------------- #
class TestParseRequirements:
    """requirements.txt -> Python dependencies with names lower-cased."""

    def test_parses_pinned_and_ranged_versions(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text(
            "\n".join(
                [
                    "# a comment",
                    "",
                    "Flask==2.0.0",
                    "requests>=2.20.0",
                    "-r other-requirements.txt",  # option line, skipped
                    "--index-url https://example.com",  # option line, skipped
                    "numpy",  # no version specifier
                ]
            ),
            encoding="utf-8",
        )

        deps = PythonDependencyParser().parse_requirements(req)
        by_name = _by_name(deps)

        assert set(by_name) == {"flask", "requests", "numpy"}
        assert by_name["flask"].version == "2.0.0"
        assert by_name["requests"].version == "2.20.0"
        assert by_name["numpy"].version == "unknown"
        assert all(d.dep_type is DependencyType.PYTHON for d in deps)

    def test_unreadable_file_yields_empty_list(self, tmp_path):
        # Missing file -> OSError branch -> deps silently dropped (empty list).
        missing = tmp_path / "does-not-exist.txt"
        assert PythonDependencyParser().parse_requirements(missing) == []


# --------------------------------------------------------------------------- #
# PythonDependencyParser.parse_pyproject
# --------------------------------------------------------------------------- #
class TestParsePyproject:
    """pyproject.toml (Poetry + PEP 621) -> Python dependencies."""

    def test_poetry_style_strips_operators_and_skips_python(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "\n".join(
                [
                    "[tool.poetry]",
                    'name = "demo"',
                    "",
                    "[tool.poetry.dependencies]",
                    'python = "^3.9"',
                    'flask = "^2.0.0"',
                    'requests = { version = ">=2.20.0" }',
                    "",
                    "[tool.poetry.dev-dependencies]",
                    'pytest = "^7.0"',
                ]
            ),
            encoding="utf-8",
        )

        deps = PythonDependencyParser().parse_pyproject(pyproject)
        by_name = _by_name(deps)

        # "python" constraint is skipped, not treated as a dependency.
        assert "python" not in by_name
        assert set(by_name) == {"flask", "requests", "pytest"}
        # Operator prefixes are stripped from the version string.
        assert by_name["flask"].version == "2.0.0"
        assert by_name["requests"].version == "2.20.0"  # from the dict form
        # dev-dependencies are flagged.
        assert by_name["pytest"].dev_dependency is True
        assert by_name["flask"].dev_dependency is False

    def test_pep621_style_dependencies(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "\n".join(
                [
                    "[project]",
                    'name = "demo"',
                    'dependencies = ["urllib3>=1.26.5", "click"]',
                ]
            ),
            encoding="utf-8",
        )

        deps = PythonDependencyParser().parse_pyproject(pyproject)
        by_name = _by_name(deps)

        assert set(by_name) == {"urllib3", "click"}
        assert by_name["urllib3"].version == "1.26.5"
        assert by_name["click"].version == "unknown"

    def test_malformed_toml_yields_empty_list(self, tmp_path):
        # Broad except: a malformed manifest must not abort the scan.
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("this is = = not valid toml [[[", encoding="utf-8")
        assert PythonDependencyParser().parse_pyproject(pyproject) == []


# --------------------------------------------------------------------------- #
# JavaScriptDependencyParser.parse_package_json
# --------------------------------------------------------------------------- #
class TestParsePackageJson:
    """package.json -> JavaScript dependencies, dev deps flagged."""

    def test_parses_dependencies_and_dev_dependencies(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(
            "\n".join(
                [
                    "{",
                    '  "dependencies": {"lodash": "^4.17.21", "axios": "~0.21.1"},',
                    '  "devDependencies": {"jest": ">=29.0.0"}',
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        deps = JavaScriptDependencyParser().parse_package_json(pkg)
        by_name = _by_name(deps)

        assert set(by_name) == {"lodash", "axios", "jest"}
        # Leading ^ ~ >= are stripped.
        assert by_name["lodash"].version == "4.17.21"
        assert by_name["axios"].version == "0.21.1"
        assert by_name["jest"].version == "29.0.0"
        assert by_name["jest"].dev_dependency is True
        assert by_name["lodash"].dev_dependency is False
        assert all(d.dep_type is DependencyType.JAVASCRIPT for d in deps)

    def test_malformed_json_yields_empty_list(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text("{ not valid json ", encoding="utf-8")
        assert JavaScriptDependencyParser().parse_package_json(pkg) == []


# --------------------------------------------------------------------------- #
# GradleDependencyParser.parse_build_gradle
# --------------------------------------------------------------------------- #
class TestParseBuildGradle:
    """build.gradle -> Gradle deps as 'group:artifact', test deps flagged."""

    def test_parses_implementation_api_and_test_declarations(self, tmp_path):
        gradle = tmp_path / "build.gradle"
        gradle.write_text(
            "\n".join(
                [
                    "dependencies {",
                    '    implementation "com.squareup.okhttp3:okhttp:4.9.0"',
                    "    api 'com.google.code.gson:gson:2.8.9'",
                    '    testImplementation "junit:junit:4.13.2"',
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        deps = GradleDependencyParser().parse_build_gradle(gradle)
        by_name = _by_name(deps)

        assert set(by_name) == {
            "com.squareup.okhttp3:okhttp",
            "com.google.code.gson:gson",
            "junit:junit",
        }
        assert by_name["com.squareup.okhttp3:okhttp"].version == "4.9.0"
        assert by_name["com.google.code.gson:gson"].version == "2.8.9"
        # testImplementation is recorded as a dev dependency.
        assert by_name["junit:junit"].dev_dependency is True
        assert by_name["com.squareup.okhttp3:okhttp"].dev_dependency is False
        assert all(d.dep_type is DependencyType.GRADLE for d in deps)

    def test_missing_file_yields_empty_list(self, tmp_path):
        assert GradleDependencyParser().parse_build_gradle(tmp_path / "nope.gradle") == []


# --------------------------------------------------------------------------- #
# CocoaPodsDependencyParser.parse_podfile_lock
# --------------------------------------------------------------------------- #
class TestParsePodfileLock:
    """Podfile.lock -> CocoaPods deps parsed only from the PODS: section."""

    def test_parses_pods_section_only(self, tmp_path):
        lock = tmp_path / "Podfile.lock"
        lock.write_text(
            "\n".join(
                [
                    "PODS:",
                    "  - Alamofire (5.4.3)",
                    "  - SwiftyJSON (5.0.0)",
                    "",
                    "DEPENDENCIES:",
                    "  - Alamofire (~> 5.4)",  # outside PODS -> ignored
                    "",
                    "SPEC CHECKSUMS:",
                    "  Alamofire: abc123",
                ]
            ),
            encoding="utf-8",
        )

        deps = CocoaPodsDependencyParser().parse_podfile_lock(lock)
        by_name = _by_name(deps)

        assert set(by_name) == {"Alamofire", "SwiftyJSON"}
        assert by_name["Alamofire"].version == "5.4.3"
        assert by_name["SwiftyJSON"].version == "5.0.0"
        assert all(d.dep_type is DependencyType.COCOAPODS for d in deps)

    def test_missing_file_yields_empty_list(self, tmp_path):
        assert CocoaPodsDependencyParser().parse_podfile_lock(tmp_path / "none.lock") == []


def test_parsers_are_independent_of_import_state():
    # Sanity: the parsers module is importable and its classes distinct.
    assert PythonDependencyParser is not JavaScriptDependencyParser
    assert "framework.security.supplychain.parsers" in sys.modules
