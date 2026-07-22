"""MultiLanguageVerifier — the cross-language orchestrator.

Extracted from verifier.py; wires together the per-language verifiers and
aggregates their results. Behaviour is unchanged.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.verification.base import LanguageVerifier, VerificationResult
from framework.verification.go_verifier import GoVerifier
from framework.verification.javascript_verifier import JavaScriptVerifier
from framework.verification.kotlin_verifier import KotlinVerifier
from framework.verification.python_verifier import PythonVerifier
from framework.verification.ruby_verifier import RubyVerifier
from framework.verification.swift_verifier import SwiftVerifier


class MultiLanguageVerifier:
    """
    Multi-Language Verification Engine

    Verifies test code across all supported programming languages.
    """

    def __init__(self) -> None:
        self.verifiers: List[LanguageVerifier] = [
            PythonVerifier(),
            KotlinVerifier(),
            SwiftVerifier(),
            JavaScriptVerifier(),
            GoVerifier(),
            RubyVerifier(),
        ]

    def verify_file(self, file_path: Path) -> Optional[VerificationResult]:
        """Verify a single file"""
        for verifier in self.verifiers:
            if verifier.supports_file(file_path):
                return verifier.verify(file_path)
        return None

    def verify_directory(
        self, directory: Path, recursive: bool = True, exclude_patterns: Optional[List[str]] = None
    ) -> List[VerificationResult]:
        """Verify all files in a directory"""
        results = []
        exclude = exclude_patterns or ["node_modules", "venv", ".git", "__pycache__"]

        def should_exclude(path: Path) -> bool:
            return any(ex in str(path) for ex in exclude)

        if recursive:
            files = directory.rglob("*")
        else:
            files = directory.glob("*")

        for file_path in files:
            if file_path.is_file() and not should_exclude(file_path):
                result = self.verify_file(file_path)
                if result:
                    results.append(result)

        return results

    def get_summary(self, results: List[VerificationResult]) -> Dict[str, Any]:
        """Get verification summary"""
        total_files = len(results)
        passed = len([r for r in results if r.success])
        failed = total_files - passed
        total_errors = sum(r.error_count for r in results)
        total_warnings = sum(r.warning_count for r in results)

        by_language = {}
        for result in results:
            if result.language not in by_language:
                by_language[result.language] = {"files": 0, "passed": 0, "errors": 0, "warnings": 0}
            by_language[result.language]["files"] += 1
            if result.success:
                by_language[result.language]["passed"] += 1
            by_language[result.language]["errors"] += result.error_count
            by_language[result.language]["warnings"] += result.warning_count

        return {
            "total_files": total_files,
            "passed": passed,
            "failed": failed,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "pass_rate": (passed / total_files * 100) if total_files > 0 else 0,
            "by_language": by_language,
        }

    def export_report(self, results: List[VerificationResult], output_path: Path) -> None:
        """Export verification report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "summary": self.get_summary(results),
            "results": [r.to_dict() for r in results],
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
