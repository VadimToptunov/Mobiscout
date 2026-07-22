"""Analyzer extracted from runtime_protection (mechanical split; see runtime/base.py)."""

from pathlib import Path

from framework.security.runtime.base import (
    ProtectionCategory,
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

    def __init__(self) -> None:
        self.android_analyzer = AndroidProtectionAnalyzer()
        self.ios_analyzer = IOSProtectionAnalyzer()

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
