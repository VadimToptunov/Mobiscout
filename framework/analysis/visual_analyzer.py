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

    def __init__(self, baseline_dir: Path) -> None:
        """
        Initialize visual analyzer

        Args:
            baseline_dir: Directory containing baseline screenshots
        """
        self.baseline_dir = baseline_dir
        self.diffs: List[VisualDiff] = []
        # Every comparison, regression or not. self.diffs holds only the
        # regressions, so it cannot answer "how many screens were compared" or
        # "how many passed" — the HTML report used to ask it anyway.
        self.results: List[VisualDiff] = []

    def compare_screenshots(
        self, screen_name: str, current_image: Path, threshold: float = 0.01
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
            threshold=threshold,
        )

        self.results.append(diff)
        if diff.has_regression:
            self.diffs.append(diff)

        return diff

    def _calculate_diff(self, baseline: Path, current: Path) -> float:
        """Real per-pixel difference (0–100%) between two screenshots via Pillow.

        Both images are converted to RGB; a differently-sized current capture is
        resized to the baseline so it still compares. The metric is the mean
        absolute per-channel difference as a percentage — 0% for identical images,
        higher the more they diverge. (Previously this compared *file sizes*, which
        is meaningless: two different images of equal size scored 0%.)
        """
        try:
            from PIL import Image, ImageChops

            with Image.open(baseline) as b_img, Image.open(current) as c_img:
                base = b_img.convert("RGB")
                cur = c_img.convert("RGB")
                if cur.size != base.size:
                    cur = cur.resize(base.size)
                diff = ImageChops.difference(base, cur)
                hist = diff.histogram()  # 256 bins per RGB channel
                total = sum(value * hist[channel * 256 + value] for channel in range(3) for value in range(256))
                max_total = base.size[0] * base.size[1] * 3 * 255
                return min((total / max_total) * 100, 100.0) if max_total else 0.0
        except (OSError, ValueError) as e:
            logger.error(f"Error calculating visual diff: {e}")
            return 0.0

    def _find_diff_regions(self, baseline: Path, current: Path) -> List[Tuple[int, int, int, int]]:
        """The bounding box of the changed area, as one ``(x, y, width, height)``
        region (via Pillow). Empty when the images match or can't be read."""
        try:
            from PIL import Image, ImageChops

            with Image.open(baseline) as b_img, Image.open(current) as c_img:
                base = b_img.convert("RGB")
                cur = c_img.convert("RGB")
                if cur.size != base.size:
                    cur = cur.resize(base.size)
                bbox = ImageChops.difference(base, cur).getbbox()
                if bbox is None:
                    return []
                left, upper, right, lower = bbox
                return [(left, upper, right - left, lower - upper)]
        except (OSError, ValueError) as e:
            logger.error(f"Error finding visual diff regions: {e}")
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

    def batch_compare(self, screenshots_dir: Path, threshold: float = 0.01) -> List[VisualDiff]:
        """
        Compare all screenshots in directory with baselines

        Args:
            screenshots_dir: Directory containing current screenshots
            threshold: Difference threshold

        Returns:
            List of visual diffs with regressions
        """
        regressions = []

        for screenshot in screenshots_dir.glob("*.png"):
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
            output_path = output_dir / f"{diff.screen_name}_diff.png"
            try:
                self._draw_diff_image(diff, output_path)
                print(f"Exported diff: {output_path}")
            except (OSError, ValueError) as e:
                print(f"Error exporting diff: {e}")

    def _draw_diff_image(self, diff: VisualDiff, output_path: Path) -> None:
        """Render the current screenshot with each changed region outlined, so a
        reviewer sees *what* changed rather than only *that* something did. With
        no regions (identical images) it writes the current frame unmarked."""
        from PIL import Image, ImageDraw

        with Image.open(diff.current_image) as img:
            canvas = img.convert("RGB")
            draw = ImageDraw.Draw(canvas)
            # Outline width scales gently with image width so it stays visible on
            # high-DPI captures without swamping small ones.
            line_width = max(2, canvas.size[0] // 400)
            for x, y, w, h in diff.diff_regions:
                draw.rectangle((x, y, x + w, y + h), outline=(255, 0, 0), width=line_width)
            canvas.save(output_path)

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
        # Counted over every comparison: self.diffs holds regressions only, so
        # "passed" was structurally 0 and "total" was the failure count.
        passed = sum(1 for d in self.results if d.is_match)
        failed = len(self.results) - passed

        diff_items = ""
        for diff in self.results:
            status = "passed" if diff.is_match else "failed"
            diff_items += f"""
        <div class="diff-item {status}">
            <h3>{diff.screen_name}</h3>
            <p>Similarity: {diff.similarity_score:.2%}</p>
            <p>Status: {"PASSED" if diff.is_match else "FAILED"}</p>
        </div>
"""

        # NB: use targeted replacement rather than str.format — the template's
        # embedded CSS contains literal `{ ... }` braces that would make
        # str.format raise KeyError (e.g. on "{ font-family").
        html = (
            html_content.replace("{total}", str(len(self.results)))
            .replace("{passed}", str(passed))
            .replace("{failed}", str(failed))
            .replace("{diff_items}", diff_items)
        )

        output_path.write_text(html)
        print(f"HTML report generated: {output_path}")
