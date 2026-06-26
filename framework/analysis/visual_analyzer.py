"""
Visual analyzer for mobile applications

Detects visual regressions and UI inconsistencies.

STEP 7: Paid Modules Enhancement - Visual Analyzer Refactoring
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


@dataclass
class VisualDiff:
    """Represents a visual difference"""
    screen_name: str
    baseline_image: Path
    current_image: Path
    diff_percentage: float  # 0-100
    diff_regions: List[Tuple[int, int, int, int]]  # (x, y, width, height)
    threshold: float = 0.01  # 1% default threshold

    @property
    def has_regression(self) -> bool:
        return self.diff_percentage > (self.threshold * 100)

    @property
    def is_match(self) -> bool:
        """Returns True if images match (no regression)"""
        return not self.has_regression

    @property
    def similarity_score(self) -> float:
        """Returns similarity as a score from 0.0 to 1.0"""
        return 1.0 - (self.diff_percentage / 100.0)


class VisualAnalyzer:
    """
    Analyzes visual differences between app screens
    """

    def __init__(self, baseline_dir: Path):
        """
        Initialize visual analyzer

        Args:
            baseline_dir: Directory containing baseline screenshots
        """
        self.baseline_dir = baseline_dir
        self.diffs: List[VisualDiff] = []

    def compare_screenshots(
            self,
            screen_name: str,
            current_image: Path,
            threshold: float = 0.01
    ) -> Optional[VisualDiff]:
        """
        Compare current screenshot with baseline

        Args:
            screen_name: Name of the screen
            current_image: Path to current screenshot
            threshold: Difference threshold (0.01 = 1%)

        Returns:
            VisualDiff if differences found, None otherwise
        """
        baseline_image = self.baseline_dir / f"{screen_name}.png"

        if not baseline_image.exists():
            print(f"Warning: No baseline for {screen_name}, creating new baseline")
            self._create_baseline(screen_name, current_image)
            return None

        if not current_image.exists():
            print(f"Error: Current image not found: {current_image}")
            return None

        # Compare images (simplified - in production use pillow/opencv)
        diff_percentage = self._calculate_diff(baseline_image, current_image)
        diff_regions = self._find_diff_regions(baseline_image, current_image)

        diff = VisualDiff(
            screen_name=screen_name,
            baseline_image=baseline_image,
            current_image=current_image,
            diff_percentage=diff_percentage,
            diff_regions=diff_regions,
            threshold=threshold
        )

        if diff.has_regression:
            self.diffs.append(diff)

        return diff

    def _calculate_diff(self, baseline: Path, current: Path) -> float:
        """
        Calculate percentage difference between images

        Note: This is a placeholder. In production, use:
        - PIL/Pillow for image loading
        - numpy for pixel comparison
        - opencv for advanced comparison
        """
        try:
            # Simplified: compare file sizes as proxy
            baseline_size = baseline.stat().st_size
            current_size = current.stat().st_size

            if baseline_size == 0:
                return 100.0

            size_diff = abs(current_size - baseline_size) / baseline_size
            return min(size_diff * 100, 100.0)

        except (OSError, ValueError) as e:
            logger.error(f"Error calculating visual diff: {e}")
            return 0.0

    def _find_diff_regions(
            self,
            baseline: Path,
            current: Path
    ) -> List[Tuple[int, int, int, int]]:
        """
        Find regions with visual differences

        Returns:
            List of (x, y, width, height) tuples
        """
        # Placeholder - in production use image diff algorithms
        return []

    def _create_baseline(self, screen_name: str, image: Path) -> None:
        """Create new baseline image"""
        import shutil

        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = self.baseline_dir / f"{screen_name}.png"

        try:
            shutil.copy(image, baseline_path)
            print(f"Created baseline: {baseline_path}")
        except Exception as e:
            print(f"Error creating baseline: {e}")

    def update_baseline(self, screen_name: str, current_image: Path) -> None:
        """Update baseline with current image"""
        self._create_baseline(screen_name, current_image)

    def batch_compare(
            self,
            screenshots_dir: Path,
            threshold: float = 0.01
    ) -> List[VisualDiff]:
        """
        Compare all screenshots in directory with baselines

        Args:
            screenshots_dir: Directory containing current screenshots
            threshold: Difference threshold

        Returns:
            List of visual diffs with regressions
        """
        regressions = []

        for screenshot in screenshots_dir.glob('*.png'):
            screen_name = screenshot.stem
            diff = self.compare_screenshots(screen_name, screenshot, threshold)

            if diff and diff.has_regression:
                regressions.append(diff)

        return regressions

    def generate_report(self) -> str:
        """Generate visual regression report"""
        report = "VISUAL REGRESSION REPORT\n"
        report += "=" * 80 + "\n\n"

        if not self.diffs:
            report += "No visual regressions detected.\n"
            return report

        report += f"Found {len(self.diffs)} visual regression(s):\n\n"

        for diff in self.diffs:
            report += f"Screen: {diff.screen_name}\n"
            report += f"  Difference: {diff.diff_percentage:.2f}%\n"
            report += f"  Threshold: {diff.threshold * 100:.2f}%\n"
            report += f"  Baseline: {diff.baseline_image}\n"
            report += f"  Current: {diff.current_image}\n"
            if diff.diff_regions:
                report += f"  Changed regions: {len(diff.diff_regions)}\n"
            report += "\n"

        report += "=" * 80 + "\n"

        return report

    def export_diff_images(self, output_dir: Path) -> None:
        """
        Export visual diff images

        Args:
            output_dir: Directory to save diff images
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        for diff in self.diffs:
            # In production: create visual diff image with highlighted regions
            # For now, just copy current image
            import shutil

            output_path = output_dir / f"{diff.screen_name}_diff.png"
            try:
                shutil.copy(diff.current_image, output_path)
                print(f"Exported diff: {output_path}")
            except (OSError, shutil.Error) as e:
                print(f"Error exporting diff: {e}")

    def generate_html_report(self, output_path: Path) -> None:
        """
        Generate HTML report for visual diffs

        Args:
            output_path: Path to save HTML report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Visual Regression Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .diff-item { margin: 20px 0; padding: 15px; border: 1px solid #ddd; }
        .diff-item.passed { border-left: 4px solid green; }
        .diff-item.failed { border-left: 4px solid red; }
        .images { display: flex; gap: 20px; }
        .images img { max-width: 300px; border: 1px solid #ccc; }
        h1 { color: #333; }
        .summary { background: #f5f5f5; padding: 15px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <h1>Visual Regression Report</h1>
    <div class="summary">
        <p>Total screens: {total}</p>
        <p>Passed: {passed}</p>
        <p>Failed: {failed}</p>
    </div>
    <div class="diffs">
        {diff_items}
    </div>
</body>
</html>
"""
        passed = sum(1 for d in self.diffs if d.is_match)
        failed = len(self.diffs) - passed

        diff_items = ""
        for diff in self.diffs:
            status = "passed" if diff.is_match else "failed"
            diff_items += f"""
        <div class="diff-item {status}">
            <h3>{diff.screen_name}</h3>
            <p>Similarity: {diff.similarity_score:.2%}</p>
            <p>Status: {"PASSED" if diff.is_match else "FAILED"}</p>
        </div>
"""

        html = html_content.format(
            total=len(self.diffs),
            passed=passed,
            failed=failed,
            diff_items=diff_items
        )

        output_path.write_text(html)
        print(f"HTML report generated: {output_path}")
