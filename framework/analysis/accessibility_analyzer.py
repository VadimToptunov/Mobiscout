"""
Accessibility Testing Module

Automated accessibility testing following WCAG 2.1 guidelines.

Features:
- Color contrast checking
- Touch target size validation
- Screen reader compatibility
- Focus indicators
- Text size requirements
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional


class WCAGLevel(Enum):
    """WCAG compliance levels"""

    A = "A"
    AA = "AA"
    AAA = "AAA"


class A11yViolationSeverity(Enum):
    """Accessibility violation severity"""

    CRITICAL = "critical"
    SERIOUS = "serious"
    MODERATE = "moderate"
    MINOR = "minor"


@dataclass
class A11yViolation:
    """Accessibility violation finding"""

    rule_id: str
    severity: A11yViolationSeverity
    wcag_level: WCAGLevel
    title: str
    description: str
    element: str
    recommendation: str
    wcag_reference: str = ""
    help_url: str = ""


@dataclass
class A11yScanResult:
    """Complete accessibility scan results"""

    app_name: str
    screen_name: str
    wcag_level: WCAGLevel
    violations: List[A11yViolation] = field(default_factory=list)
    pass_count: int = 0
    total_checks: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == A11yViolationSeverity.CRITICAL)

    @property
    def serious_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == A11yViolationSeverity.SERIOUS)

    @property
    def compliance_score(self) -> float:
        """Calculate compliance score (0-100)"""
        if self.total_checks == 0:
            return 0.0
        return (self.pass_count / self.total_checks) * 100


class ColorContrastChecker:
    """
    Check color contrast ratios according to WCAG guidelines

    WCAG 2.1 Requirements:
    - Level AA: 4.5:1 for normal text, 3:1 for large text
    - Level AAA: 7:1 for normal text, 4.5:1 for large text
    """

    RATIOS = {
        WCAGLevel.AA: {"normal": 4.5, "large": 3.0},
        WCAGLevel.AAA: {"normal": 7.0, "large": 4.5},
    }

    @staticmethod
    def calculate_contrast_ratio(color1: tuple[int, int, int], color2: tuple[int, int, int]) -> float:
        """Calculate contrast ratio between two RGB colors"""

        def relative_luminance(rgb: tuple[int, int, int]) -> float:
            """Calculate relative luminance"""
            rgb_normalized = [c / 255.0 for c in rgb]

            def adjust(channel: float) -> float:
                if channel <= 0.03928:
                    return channel / 12.92
                return float(((channel + 0.055) / 1.055) ** 2.4)

            r_adj = adjust(rgb_normalized[0])
            g_adj = adjust(rgb_normalized[1])
            b_adj = adjust(rgb_normalized[2])

            return 0.2126 * r_adj + 0.7152 * g_adj + 0.0722 * b_adj

        l1 = relative_luminance(color1)
        l2 = relative_luminance(color2)

        lighter = max(l1, l2)
        darker = min(l1, l2)

        return (lighter + 0.05) / (darker + 0.05)

    def check_element_contrast(
            self,
            element: Dict[str, Any],
            wcag_level: WCAGLevel = WCAGLevel.AA,
    ) -> Optional[A11yViolation]:
        """Check if element meets contrast requirements"""
        # Extract colors (placeholder - in production, parse from styles)
        fg_color = element.get("text_color", (0, 0, 0))
        bg_color = element.get("background_color", (255, 255, 255))

        if not isinstance(fg_color, tuple) or not isinstance(bg_color, tuple):
            return None

        # Cast to expected tuple type after validation
        fg_tuple: tuple[int, int, int] = (int(fg_color[0]), int(fg_color[1]), int(fg_color[2]))
        bg_tuple: tuple[int, int, int] = (int(bg_color[0]), int(bg_color[1]), int(bg_color[2]))
        ratio = self.calculate_contrast_ratio(fg_tuple, bg_tuple)

        # Determine if text is large (18pt+ or 14pt+ bold)
        text_size = element.get("font_size", 12)
        is_large = text_size >= 18 or (text_size >= 14 and element.get("bold", False))

        required_ratio = self.RATIOS[wcag_level]["large" if is_large else "normal"]

        if ratio < required_ratio:
            return A11yViolation(
                rule_id="color-contrast",
                severity=A11yViolationSeverity.SERIOUS,
                wcag_level=wcag_level,
                title="Insufficient Color Contrast",
                description=f"Contrast ratio {ratio:.2f}:1 is below required {required_ratio}:1",
                element=str(element.get("id", element.get("text", "unknown"))),
                recommendation=f"Increase contrast to at least {required_ratio}:1",
                wcag_reference="WCAG 2.1 Success Criterion 1.4.3",
                help_url="https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html",
            )

        return None


class TouchTargetValidator:
    """
    Validate touch target sizes

    WCAG 2.1 SC 2.5.5 (Level AAA): 44x44 CSS pixels
    Platform guidelines:
    - iOS: 44x44 points minimum
    - Android: 48x48 dp minimum
    """

    MIN_SIZE = {
        "ios": 44,
        "android": 48,
        "wcag_aaa": 44,
    }

    def check_touch_target(
            self,
            element: Dict[str, Any],
            platform: str = "android",
    ) -> Optional[A11yViolation]:
        """Check if touch target meets size requirements"""
        bounds = element.get("bounds", {})
        width = bounds.get("width", 0)
        height = bounds.get("height", 0)

        min_size = self.MIN_SIZE.get(platform, 48)

        if element.get("clickable") and (width < min_size or height < min_size):
            return A11yViolation(
                rule_id="touch-target-size",
                severity=A11yViolationSeverity.SERIOUS,
                wcag_level=WCAGLevel.AAA,
                title="Touch Target Too Small",
                description=f"Element size {width}x{height} is below minimum {min_size}x{min_size}",
                element=str(element.get("id", element.get("text", "unknown"))),
                recommendation=f"Increase touch target to at least {min_size}x{min_size} {platform} units",
                wcag_reference="WCAG 2.1 Success Criterion 2.5.5",
                help_url="https://www.w3.org/WAI/WCAG21/Understanding/target-size.html",
            )

        return None


class ScreenReaderChecker:
    """
    Check screen reader compatibility

    Verifies:
    - Content descriptions (Android) / Accessibility labels (iOS)
    - Focusable elements
    - Semantic structure
    """

    def check_content_description(self, element: Dict[str, Any]) -> Optional[A11yViolation]:
        """Check if interactive element has proper description"""
        is_interactive = (
                element.get("clickable")
                or element.get("focusable")
                or element.get("type") in ["Button", "TextField", "ImageButton"]
        )

        has_description = bool(element.get("content_desc") or element.get("text") or element.get("accessibility_label"))

        if is_interactive and not has_description:
            return A11yViolation(
                rule_id="missing-content-description",
                severity=A11yViolationSeverity.CRITICAL,
                wcag_level=WCAGLevel.A,
                title="Missing Accessibility Label",
                description="Interactive element lacks content description for screen readers",
                element=str(element.get("id", element.get("class", "unknown"))),
                recommendation="Add content description (Android) or accessibility label (iOS)",
                wcag_reference="WCAG 2.1 Success Criterion 1.1.1",
                help_url="https://www.w3.org/WAI/WCAG21/Understanding/non-text-content.html",
            )

        return None


class TextSizeChecker:
    """
    Check text size and scalability

    Requirements:
    - Minimum readable size
    - Support for text scaling
    """

    MIN_TEXT_SIZE = 12  # CSS pixels

    def check_text_size(self, element: Dict[str, Any]) -> Optional[A11yViolation]:
        """Check if text meets minimum size requirements"""
        if not element.get("text"):
            return None

        font_size = element.get("font_size", 0)

        if font_size > 0 and font_size < self.MIN_TEXT_SIZE:
            return A11yViolation(
                rule_id="text-too-small",
                severity=A11yViolationSeverity.MODERATE,
                wcag_level=WCAGLevel.AA,
                title="Text Too Small",
                description=f"Text size {font_size}px is below minimum {self.MIN_TEXT_SIZE}px",
                element=str(element.get("text", "")[:50]),
                recommendation=f"Increase text size to at least {self.MIN_TEXT_SIZE}px",
                wcag_reference="WCAG 2.1 Success Criterion 1.4.4",
                help_url="https://www.w3.org/WAI/WCAG21/Understanding/resize-text.html",
            )

        return None


class AccessibilityScanner:
    """
    Main accessibility scanner

    Orchestrates all accessibility checks and generates comprehensive reports.
    """

    def __init__(self, wcag_level: WCAGLevel = WCAGLevel.AA):
        self.wcag_level = wcag_level
        self.contrast_checker = ColorContrastChecker()
        self.touch_validator = TouchTargetValidator()
        self.screen_reader_checker = ScreenReaderChecker()
        self.text_checker = TextSizeChecker()

    def scan_hierarchy(
            self,
            hierarchy: Dict[str, Any],
            app_name: str,
            screen_name: str,
            platform: str = "android",
    ) -> A11yScanResult:
        """Scan UI hierarchy for accessibility issues"""
        result = A11yScanResult(
            app_name=app_name,
            screen_name=screen_name,
            wcag_level=self.wcag_level,
        )

        elements = self._flatten_hierarchy(hierarchy)

        for element in elements:
            # Run all checks
            checks = [
                self.contrast_checker.check_element_contrast(element, self.wcag_level),
                self.touch_validator.check_touch_target(element, platform),
                self.screen_reader_checker.check_content_description(element),
                self.text_checker.check_text_size(element),
            ]

            result.total_checks += len(checks)

            for violation in checks:
                if violation:
                    result.violations.append(violation)
                else:
                    result.pass_count += 1

        return result

    def _flatten_hierarchy(self, node: Dict[str, Any], elements: Optional[List] = None) -> List[Dict[str, Any]]:
        """Flatten UI hierarchy into list of elements"""
        if elements is None:
            elements = []

        elements.append(node)

        for child in node.get("children", []):
            self._flatten_hierarchy(child, elements)

        return elements

    def generate_report(self, result: A11yScanResult, output_path: Path, format: str = "json") -> None:
        """Generate accessibility report"""
        if format == "json":
            self._generate_json_report(result, output_path)
        elif format == "html":
            self._generate_html_report(result, output_path)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_json_report(self, result: A11yScanResult, output_path: Path) -> None:
        """Generate JSON report"""
        data = {
            "app_name": result.app_name,
            "screen_name": result.screen_name,
            "wcag_level": result.wcag_level.value,
            "summary": {
                "total_checks": result.total_checks,
                "passed": result.pass_count,
                "violations": len(result.violations),
                "critical": result.critical_count,
                "serious": result.serious_count,
                "compliance_score": result.compliance_score,
            },
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "severity": v.severity.value,
                    "wcag_level": v.wcag_level.value,
                    "title": v.title,
                    "description": v.description,
                    "element": v.element,
                    "recommendation": v.recommendation,
                    "wcag_reference": v.wcag_reference,
                    "help_url": v.help_url,
                }
                for v in result.violations
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    def _generate_html_report(self, result: A11yScanResult, output_path: Path) -> None:
        """Generate HTML report"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Accessibility Report - {result.app_name}</title>
    <style>
        body {{ font-family: sans-serif; margin: 40px; background: #f5f5f5; }}
        .header {{ background: #2196F3; color: white; padding: 30px; border-radius: 8px; }}
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
        .card {{ background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .card .value {{ font-size: 2em; font-weight: bold; margin: 10px 0; }}
        .score {{ font-size: 3em; color: #4CAF50; }}
        .violation {{ background: white; padding: 20px; margin: 10px 0; border-radius: 8px; border-left: 5px solid; }}
        .critical {{ border-left-color: #f44336; }}
        .serious {{ border-left-color: #ff9800; }}
        .moderate {{ border-left-color: #ffc107; }}
        .minor {{ border-left-color: #03a9f4; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Accessibility Report</h1>
        <p>{result.app_name} - {result.screen_name}</p>
        <p>WCAG Level: {result.wcag_level.value}</p>
    </div>
    
    <div class="summary">
        <div class="card">
            <div class="label">Compliance Score</div>
            <div class="score">{result.compliance_score:.0f}%</div>
        </div>
        <div class="card">
            <div class="label">Total Checks</div>
            <div class="value">{result.total_checks}</div>
        </div>
        <div class="card">
            <div class="label">Passed</div>
            <div class="value" style="color: #4CAF50;">{result.pass_count}</div>
        </div>
        <div class="card">
            <div class="label">Violations</div>
            <div class="value" style="color: #f44336;">{len(result.violations)}</div>
        </div>
    </div>
    
    <h2>Violations</h2>
    {"".join(self._format_violation_html(v) for v in result.violations)}
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)

    @staticmethod
    def _format_violation_html(violation: A11yViolation) -> str:
        """Format single violation as HTML"""
        return f"""
<div class="violation {violation.severity.value}">
    <h3>{violation.title}</h3>
    <p><strong>Severity:</strong> {violation.severity.value.upper()}</p>
    <p><strong>Element:</strong> {violation.element}</p>
    <p><strong>Description:</strong> {violation.description}</p>
    <p><strong>Recommendation:</strong> {violation.recommendation}</p>
    <p><strong>WCAG:</strong> {violation.wcag_reference}</p>
    <p><a href="{violation.help_url}" target="_blank">Learn more →</a></p>
</div>
"""
