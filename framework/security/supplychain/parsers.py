"""Extracted from supply_chain (mechanical split; see supplychain/base.py)."""

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

from framework.security.supplychain.base import (
    DependencyType,
    VulnerabilitySeverity,
    LicenseType,
    Dependency,
    Vulnerability,
    SupplyChainFinding,
    DependencyWithVulns,
    VulnerabilityInfo,
    LicenseIssue,
    SupplyChainResult,
)


class PythonDependencyParser:
    """
    Python Dependency Parser

    Parses requirements.txt, setup.py, pyproject.toml, Pipfile
    """

    # Known vulnerable packages (simplified - in production use PyPI Advisory Database)
    KNOWN_VULNERABILITIES = {
        "pyyaml": [
            ("< 5.4", "CVE-2020-14343", VulnerabilitySeverity.CRITICAL, "Arbitrary code execution via yaml.load()"),
        ],
        "django": [
            ("< 3.2.4", "CVE-2021-33203", VulnerabilitySeverity.MEDIUM, "Potential directory traversal"),
        ],
        "flask": [
            ("< 2.0.0", "CVE-2019-1010083", VulnerabilitySeverity.HIGH, "Denial of service via crafted JSON"),
        ],
        "requests": [
            ("< 2.20.0", "CVE-2018-18074", VulnerabilitySeverity.MEDIUM, "Information disclosure"),
        ],
        "urllib3": [
            ("< 1.26.5", "CVE-2021-33503", VulnerabilitySeverity.HIGH, "ReDoS vulnerability"),
        ],
        "pillow": [
            ("< 8.2.0", "CVE-2021-27921", VulnerabilitySeverity.HIGH, "Buffer overflow"),
        ],
        "cryptography": [
            ("< 3.3.2", "CVE-2020-36242", VulnerabilitySeverity.HIGH, "Integer overflow"),
        ],
        "jinja2": [
            ("< 2.11.3", "CVE-2020-28493", VulnerabilitySeverity.MEDIUM, "ReDoS via regex"),
        ],
    }

    # License classification
    PERMISSIVE_LICENSES = ["MIT", "Apache", "BSD", "ISC", "Unlicense", "WTFPL", "Zlib"]

    COPYLEFT_LICENSES = ["GPL", "LGPL", "AGPL", "MPL", "CC-BY-SA"]

    def parse_requirements(self, requirements_path: Path) -> List[Dependency]:
        """Parse requirements.txt"""
        dependencies = []

        try:
            content = requirements_path.read_text()
            for line in content.splitlines():
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Skip options
                if line.startswith("-"):
                    continue

                # Parse package==version or package>=version
                match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*([<>=!]+)?\s*(.+)?$", line)
                if match:
                    name = match.group(1)
                    version = match.group(3) or "unknown"

                    dependencies.append(
                        Dependency(
                            name=name.lower(),
                            version=version,
                            dep_type=DependencyType.PYTHON,
                        )
                    )

        except OSError:
            pass

        return dependencies

    def parse_pyproject(self, pyproject_path: Path) -> List[Dependency]:
        """Parse pyproject.toml"""
        dependencies = []

        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # Fallback
            except ImportError:
                return dependencies

        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)

            # Poetry style
            if "tool" in data and "poetry" in data["tool"]:
                poetry = data["tool"]["poetry"]
                for name, spec in poetry.get("dependencies", {}).items():
                    if name == "python":
                        continue
                    version = spec if isinstance(spec, str) else spec.get("version", "unknown")
                    dependencies.append(
                        Dependency(
                            name=name.lower(),
                            version=version.lstrip("^~>=<"),
                            dep_type=DependencyType.PYTHON,
                        )
                    )

                for name, spec in poetry.get("dev-dependencies", {}).items():
                    version = spec if isinstance(spec, str) else spec.get("version", "unknown")
                    dependencies.append(
                        Dependency(
                            name=name.lower(),
                            version=version.lstrip("^~>=<"),
                            dep_type=DependencyType.PYTHON,
                            dev_dependency=True,
                        )
                    )

            # PEP 621 style
            if "project" in data:
                for dep in data["project"].get("dependencies", []):
                    match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*([<>=!]+)?\s*(.+)?$", dep)
                    if match:
                        dependencies.append(
                            Dependency(
                                name=match.group(1).lower(),
                                version=match.group(3) or "unknown",
                                dep_type=DependencyType.PYTHON,
                            )
                        )

        except (OSError, Exception):
            pass

        return dependencies


class JavaScriptDependencyParser:
    """
    JavaScript/Node.js Dependency Parser

    Parses package.json and package-lock.json
    """

    # Known npm vulnerabilities (simplified)
    KNOWN_VULNERABILITIES = {
        "lodash": [
            ("< 4.17.21", "CVE-2021-23337", VulnerabilitySeverity.HIGH, "Command injection via template"),
        ],
        "axios": [
            ("< 0.21.1", "CVE-2020-28168", VulnerabilitySeverity.MEDIUM, "SSRF vulnerability"),
        ],
        "minimist": [
            ("< 1.2.3", "CVE-2020-7598", VulnerabilitySeverity.MEDIUM, "Prototype pollution"),
        ],
        "node-fetch": [
            ("< 2.6.1", "CVE-2020-15168", VulnerabilitySeverity.MEDIUM, "Denial of service"),
        ],
        "serialize-javascript": [
            ("< 3.1.0", "CVE-2020-7660", VulnerabilitySeverity.CRITICAL, "Remote code execution"),
        ],
    }

    def parse_package_json(self, package_path: Path) -> List[Dependency]:
        """Parse package.json"""
        dependencies = []

        try:
            with open(package_path, "r") as f:
                data = json.load(f)

            # Production dependencies
            for name, version in data.get("dependencies", {}).items():
                dependencies.append(
                    Dependency(
                        name=name,
                        version=version.lstrip("^~>=<"),
                        dep_type=DependencyType.JAVASCRIPT,
                    )
                )

            # Dev dependencies
            for name, version in data.get("devDependencies", {}).items():
                dependencies.append(
                    Dependency(
                        name=name,
                        version=version.lstrip("^~>=<"),
                        dep_type=DependencyType.JAVASCRIPT,
                        dev_dependency=True,
                    )
                )

        except (OSError, json.JSONDecodeError):
            pass

        return dependencies


class GradleDependencyParser:
    """
    Gradle Dependency Parser

    Parses build.gradle and build.gradle.kts
    """

    # Known Java/Android vulnerabilities (simplified)
    KNOWN_VULNERABILITIES = {
        "com.squareup.okhttp3:okhttp": [
            ("< 4.9.0", "CVE-2021-0341", VulnerabilitySeverity.HIGH, "Certificate validation bypass"),
        ],
        "com.google.code.gson:gson": [
            ("< 2.8.9", "CVE-2022-25647", VulnerabilitySeverity.HIGH, "Denial of service"),
        ],
        "org.apache.logging.log4j:log4j-core": [
            ("< 2.17.0", "CVE-2021-44228", VulnerabilitySeverity.CRITICAL, "Remote code execution (Log4Shell)"),
        ],
    }

    def parse_build_gradle(self, gradle_path: Path) -> List[Dependency]:
        """Parse build.gradle"""
        dependencies = []

        try:
            content = gradle_path.read_text()

            # Match implementation/api/compile declarations
            patterns = [
                r'implementation\s*["\']([^:]+):([^:]+):([^"\']+)["\']',
                r'api\s*["\']([^:]+):([^:]+):([^"\']+)["\']',
                r'compile\s*["\']([^:]+):([^:]+):([^"\']+)["\']',
                r'testImplementation\s*["\']([^:]+):([^:]+):([^"\']+)["\']',
            ]

            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    group = match.group(1)
                    artifact = match.group(2)
                    version = match.group(3)

                    dependencies.append(
                        Dependency(
                            name=f"{group}:{artifact}",
                            version=version,
                            dep_type=DependencyType.GRADLE,
                            dev_dependency="test" in pattern.lower(),
                        )
                    )

        except OSError:
            pass

        return dependencies


class CocoaPodsDependencyParser:
    """
    CocoaPods Dependency Parser

    Parses Podfile and Podfile.lock
    """

    def parse_podfile_lock(self, podfile_lock_path: Path) -> List[Dependency]:
        """Parse Podfile.lock"""
        dependencies = []

        try:
            content = podfile_lock_path.read_text()

            # Parse PODS section
            in_pods_section = False
            for line in content.splitlines():
                if line.strip() == "PODS:":
                    in_pods_section = True
                    continue
                elif line.strip().endswith(":") and not line.startswith(" "):
                    in_pods_section = False
                    continue

                if in_pods_section and line.startswith("  - "):
                    # Parse "  - PodName (version)"
                    match = re.match(r"\s+-\s+([^\s(]+)\s*\(([^)]+)\)", line)
                    if match:
                        dependencies.append(
                            Dependency(
                                name=match.group(1),
                                version=match.group(2),
                                dep_type=DependencyType.COCOAPODS,
                            )
                        )

        except OSError:
            pass

        return dependencies
