"""Analyzer extracted from runtime_protection (mechanical split; see runtime/base.py)."""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from framework.security.runtime.base import (
    ProtectionCategory,
    ImplementationQuality,
    ProtectionIndicator,
    ProtectionAnalysis,
    ProtectionStatus,
    BypassMethod,
    RuntimeProtectionResult,
    QuickCheckResult,
)

from framework.security.runtime.android import AndroidProtectionAnalyzer
from framework.security.runtime.ios import IOSProtectionAnalyzer


class RuntimeProtectionAnalyzer:
    """
    Comprehensive Runtime Protection Analyzer

    Analyzes mobile apps for runtime protection implementations.
    """

    def __init__(self):
        self.android_analyzer = AndroidProtectionAnalyzer()
        self.ios_analyzer = IOSProtectionAnalyzer()

    def analyze(self, source_dir: Path, platform: str = "all") -> Dict[str, List[ProtectionAnalysis]]:
        """Analyze source for runtime protections"""
        results = {}

        if platform in ["android", "all"]:
            results["android"] = self.android_analyzer.analyze_source(source_dir)

        if platform in ["ios", "all"]:
            results["ios"] = self.ios_analyzer.analyze_source(source_dir)

        return results

    def get_summary(self, results: Dict[str, List[ProtectionAnalysis]]) -> Dict[str, Any]:
        """Get analysis summary"""
        summary = {
            "platforms": {},
            "overall_score": 0.0,
            "recommendations": [],
        }

        total_score = 0
        total_categories = 0

        for platform, analyses in results.items():
            platform_score = 0
            platform_summary = {
                "implemented": 0,
                "strong": 0,
                "moderate": 0,
                "weak": 0,
                "none": 0,
            }

            for analysis in analyses:
                if analysis.implemented:
                    platform_summary["implemented"] += 1
                    platform_score += analysis.score

                    if analysis.quality == ImplementationQuality.STRONG:
                        platform_summary["strong"] += 1
                    elif analysis.quality == ImplementationQuality.MODERATE:
                        platform_summary["moderate"] += 1
                    elif analysis.quality == ImplementationQuality.WEAK:
                        platform_summary["weak"] += 1
                else:
                    platform_summary["none"] += 1

                # Collect recommendations
                for rec in analysis.recommendations:
                    if rec not in summary["recommendations"]:
                        summary["recommendations"].append(rec)

                total_categories += 1

            if len(analyses) > 0:
                platform_summary["average_score"] = platform_score / len(analyses)
                total_score += platform_score

            summary["platforms"][platform] = platform_summary

        if total_categories > 0:
            summary["overall_score"] = total_score / total_categories

        return summary

    def export_report(self, results: Dict[str, List[ProtectionAnalysis]], output_path: Path) -> None:
        """Export protection analysis report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "summary": self.get_summary(results),
            "details": {platform: [a.to_dict() for a in analyses] for platform, analyses in results.items()},
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    def generate_html_report(self, results: Dict[str, List[ProtectionAnalysis]], output_path: Path) -> None:
        """Generate HTML report"""
        summary = self.get_summary(results)

        html = (
            """
<!DOCTYPE html>
<html>
<head>
    <title>Runtime Protection Analysis</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        h1 { color: #333; }
        .score { font-size: 48px; font-weight: bold; color: #007bff; }
        .category { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 4px; }
        .implemented { border-left: 4px solid #28a745; }
        .not-implemented { border-left: 4px solid #dc3545; }
        .quality-strong { color: #28a745; }
        .quality-moderate { color: #ffc107; }
        .quality-weak { color: #dc3545; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #007bff; color: white; }
        .indicator { background: #f8f9fa; padding: 8px; margin: 5px 0; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Runtime Protection Analysis Report</h1>
        <div class="score">Score: """
            + f"{summary['overall_score']:.1f}"
            + """/100</div>
"""
        )

        for platform, analyses in results.items():
            html += f"<h2>{platform.upper()} Platform</h2>"

            for analysis in analyses:
                impl_class = "implemented" if analysis.implemented else "not-implemented"
                quality_class = f"quality-{analysis.quality.value}"

                html += f"""
                <div class="category {impl_class}">
                    <h3>{analysis.category.value.replace('_', ' ').title()}</h3>
                    <p>Status: <span class="{quality_class}">{analysis.quality.value.upper()}</span>
                    | Score: {analysis.score:.1f}/100</p>
"""

                if analysis.indicators:
                    html += "<h4>Indicators Found:</h4>"
                    for ind in analysis.indicators[:5]:
                        html += f"""
                        <div class="indicator">
                            <strong>{ind.description}</strong> ({ind.bypass_difficulty} bypass)
                            <br><small>{ind.location}:{ind.line_number}</small>
                        </div>
"""

                if analysis.recommendations:
                    html += "<h4>Recommendations:</h4><ul>"
                    for rec in analysis.recommendations:
                        html += f"<li>{rec}</li>"
                    html += "</ul>"

                html += "</div>"

        html += """
    </div>
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)

    def analyze(self, app_path: Path, platform: str) -> RuntimeProtectionResult:
        """
        Analyze app binary for runtime protections.

        This method returns a RuntimeProtectionResult for CLI compatibility.
        """
        # Use the source analysis and convert to CLI-compatible result
        analyses = []
        if platform == "android":
            analyses = self.android_analyzer.analyze_source(app_path.parent if app_path.is_file() else app_path)
        else:
            analyses = self.ios_analyzer.analyze_source(app_path.parent if app_path.is_file() else app_path)

        result = RuntimeProtectionResult()
        all_recommendations = []

        # Map analyses to result attributes
        for analysis in analyses:
            status = ProtectionStatus(
                detected=analysis.implemented,
                strength=analysis.quality.value if analysis.implemented else "none",
                details=f"Score: {analysis.score:.0f}%, {len(analysis.indicators)} indicators found",
            )

            if analysis.category == ProtectionCategory.ROOT_DETECTION:
                result.root_detection = status
            elif analysis.category == ProtectionCategory.JAILBREAK_DETECTION:
                result.root_detection = status  # Map jailbreak to root for unified interface
            elif analysis.category == ProtectionCategory.EMULATOR_DETECTION:
                result.emulator_detection = status
            elif analysis.category == ProtectionCategory.DEBUG_DETECTION:
                result.debug_detection = status
            elif analysis.category == ProtectionCategory.TAMPER_DETECTION:
                result.tamper_detection = status
            elif analysis.category in [ProtectionCategory.HOOK_DETECTION, ProtectionCategory.FRIDA_DETECTION]:
                result.hook_detection = status
            elif analysis.category == ProtectionCategory.SSL_PINNING:
                result.ssl_pinning = status
            elif analysis.category == ProtectionCategory.OBFUSCATION:
                result.obfuscation = status

            all_recommendations.extend(analysis.recommendations)

        result.recommendations = list(set(all_recommendations))[:10]

        # Calculate overall score
        protections = [
            result.root_detection,
            result.emulator_detection,
            result.debug_detection,
            result.tamper_detection,
            result.hook_detection,
            result.ssl_pinning,
            result.obfuscation,
        ]
        detected_count = sum(1 for p in protections if p.detected)
        result.score = (detected_count / len(protections)) * 100

        # Add potential bypass methods for missing protections
        if not result.root_detection.detected:
            result.bypass_methods.append(
                BypassMethod(
                    method="Root/Jailbreak bypass",
                    description="App can run on rooted/jailbroken devices without detection",
                    difficulty="easy",
                )
            )
        if not result.hook_detection.detected:
            result.bypass_methods.append(
                BypassMethod(
                    method="Frida/Xposed hooking",
                    description="App vulnerable to runtime instrumentation frameworks",
                    difficulty="easy",
                )
            )
        if not result.debug_detection.detected:
            result.bypass_methods.append(
                BypassMethod(
                    method="Debugger attachment",
                    description="App can be debugged to analyze runtime behavior",
                    difficulty="easy",
                )
            )

        return result

    def quick_check(self, app_path: Path, platform: str) -> QuickCheckResult:
        """
        Quick check for protection mechanisms.

        Returns a simple result with boolean flags.
        """
        full_result = self.analyze(app_path, platform)

        return QuickCheckResult(
            has_root_detection=full_result.root_detection.detected,
            has_emulator_detection=full_result.emulator_detection.detected,
            has_debug_detection=full_result.debug_detection.detected,
            has_tamper_detection=full_result.tamper_detection.detected,
            has_ssl_pinning=full_result.ssl_pinning.detected,
            has_obfuscation=full_result.obfuscation.detected,
        )

    def export_html(self, result: RuntimeProtectionResult, output_path: Path) -> None:
        """Export RuntimeProtectionResult to HTML report"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Runtime Protection Analysis Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        .score {{ font-size: 48px; font-weight: bold; text-align: center; padding: 20px; }}
        .score.excellent {{ color: #28a745; }}
        .score.good {{ color: #17a2b8; }}
        .score.moderate {{ color: #ffc107; }}
        .score.weak {{ color: #dc3545; }}
        .protection {{ display: flex; justify-content: space-between; padding: 15px; border: 1px solid #ddd; margin: 10px 0; border-radius: 4px; }}
        .protection.detected {{ border-left: 4px solid #28a745; }}
        .protection.missing {{ border-left: 4px solid #dc3545; background: #fff5f5; }}
        .status {{ font-weight: bold; }}
        .status.detected {{ color: #28a745; }}
        .status.missing {{ color: #dc3545; }}
        .strength {{ color: #666; font-size: 14px; }}
        .recommendations {{ background: #e7f3ff; padding: 15px; border-radius: 4px; margin-top: 20px; }}
        .bypass {{ background: #fff3cd; padding: 10px; margin: 5px 0; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Runtime Protection Analysis</h1>
        <div class="score {'excellent' if result.score >= 80 else 'good' if result.score >= 60 else 'moderate' if result.score >= 40 else 'weak'}">
            {result.score:.0f}%
        </div>

        <h2>Protection Mechanisms</h2>
"""

        protections = [
            ("Root/Jailbreak Detection", result.root_detection),
            ("Emulator Detection", result.emulator_detection),
            ("Debug Detection", result.debug_detection),
            ("Tamper Detection", result.tamper_detection),
            ("Hook Detection", result.hook_detection),
            ("SSL Pinning", result.ssl_pinning),
            ("Code Obfuscation", result.obfuscation),
        ]

        for name, prot in protections:
            status_class = "detected" if prot.detected else "missing"
            status_text = "✓ Detected" if prot.detected else "✗ Missing"
            html += f"""
        <div class="protection {status_class}">
            <div>
                <strong>{name}</strong>
                <div class="strength">Strength: {prot.strength.upper()}</div>
            </div>
            <div class="status {status_class}">{status_text}</div>
        </div>
"""

        if result.recommendations:
            html += """
        <div class="recommendations">
            <h3>Recommendations</h3>
            <ul>
"""
            for rec in result.recommendations:
                html += f"            <li>{rec}</li>\n"
            html += """
            </ul>
        </div>
"""

        if result.bypass_methods:
            html += """
        <h3>Potential Bypass Methods</h3>
"""
            for bypass in result.bypass_methods:
                html += f"""
        <div class="bypass">
            <strong>{bypass.method}</strong> ({bypass.difficulty})
            <p>{bypass.description}</p>
        </div>
"""

        html += """
    </div>
</body>
</html>
"""

        with open(output_path, "w") as f:
            f.write(html)
