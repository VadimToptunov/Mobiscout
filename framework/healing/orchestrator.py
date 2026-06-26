"""
Healing orchestrator

Coordinates the healing process from failure detection to file update.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .element_matcher import ElementMatcher, MatchResult
from .failure_analyzer import FailureAnalyzer, SelectorFailure
from .file_updater import FileUpdater, UpdateResult
from .git_integration import GitIntegration
from .selector_discovery import SelectorDiscovery


@dataclass
class HealingResult:
    """Complete result of healing operation"""
    failure: SelectorFailure
    alternatives_found: int
    best_match: Optional[MatchResult]
    update_result: Optional[UpdateResult]
    success: bool
    error_message: Optional[str] = None


class HealingOrchestrator:
    """
    Orchestrates the complete healing process
    """

    def __init__(
            self,
            repo_path: Path,
            ml_model_path: Optional[Path] = None,
            min_confidence: float = 0.7
    ):
        """
        Initialize healing orchestrator

        Args:
            repo_path: Path to repository root
            ml_model_path: Path to ML model
            min_confidence: Minimum confidence threshold for healing
        """
        self.repo_path = repo_path
        self.min_confidence = min_confidence

        self.failure_analyzer = FailureAnalyzer()
        self.selector_discovery = SelectorDiscovery()
        self.element_matcher = ElementMatcher(ml_model_path)
        self.file_updater = FileUpdater(create_backup=True)
        self.git_integration = GitIntegration(repo_path)

    def analyze_failures(
            self,
            junit_path: Path,
            screenshots_dir: Optional[Path] = None,
            page_source_dir: Optional[Path] = None,
            page_objects_dir: Optional[Path] = None
    ) -> List[SelectorFailure]:
        """
        Analyze test failures

        Args:
            junit_path: Path to JUnit XML results
            screenshots_dir: Directory with failure screenshots
            page_source_dir: Directory with page source dumps
            page_objects_dir: Directory with Page Object files

        Returns:
            List of selector failures
        """
        failures = self.failure_analyzer.analyze_junit_results(junit_path)

        # Enrich with additional data
        if screenshots_dir and screenshots_dir.exists():
            self.failure_analyzer.enrich_with_screenshots(screenshots_dir)

        if page_source_dir and page_source_dir.exists():
            self.failure_analyzer.enrich_with_page_source(page_source_dir)

        if page_objects_dir and page_objects_dir.exists():
            self.failure_analyzer.enrich_with_page_objects(page_objects_dir)

        return failures

    def heal_failure(
            self,
            failure: SelectorFailure,
            dry_run: bool = False
    ) -> HealingResult:
        """
        Heal a single failure

        Args:
            failure: Selector failure to heal
            dry_run: If True, don't actually update files

        Returns:
            HealingResult with details
        """
        # Check if we have page source
        if not failure.page_source_path or not failure.page_source_path.exists():
            return HealingResult(
                failure=failure,
                alternatives_found=0,
                best_match=None,
                update_result=None,
                success=False,
                error_message="No page source available"
            )

        # Discover alternative selectors
        alternatives = self.selector_discovery.discover_from_page_source(
            failure.page_source_path,
            failure.selector_tuple
        )

        if not alternatives:
            return HealingResult(
                failure=failure,
                alternatives_found=0,
                best_match=None,
                update_result=None,
                success=False,
                error_message="No alternative selectors found"
            )

        # Find best match using ML
        best_match = self.element_matcher.find_best_match(
            alternatives,
            expected_element_type=None,
            context={'screen_name': failure.test_name}
        )

        if not best_match:
            return HealingResult(
                failure=failure,
                alternatives_found=len(alternatives),
                best_match=None,
                update_result=None,
                success=False,
                error_message="No suitable match found"
            )

        # Check confidence threshold
        if best_match.combined_confidence < self.min_confidence:
            return HealingResult(
                failure=failure,
                alternatives_found=len(alternatives),
                best_match=best_match,
                update_result=None,
                success=False,
                error_message=f"Confidence too low: {best_match.combined_confidence:.2f} < {self.min_confidence}"
            )

        # Update file (if not dry run)
        update_result = None
        if not dry_run and failure.page_object_file:
            update_result = self.file_updater.update_selector(
                failure.page_object_file,
                failure.element_name or "unknown_element",
                failure.selector_tuple,
                best_match.selector.selector_tuple,
                best_match.combined_confidence
            )

        return HealingResult(
            failure=failure,
            alternatives_found=len(alternatives),
            best_match=best_match,
            update_result=update_result,
            success=True if dry_run else (update_result.success if update_result else False)
        )

    def heal_all(
            self,
            failures: List[SelectorFailure],
            dry_run: bool = False,
            auto_commit: bool = False,
            branch_name: Optional[str] = None
    ) -> List[HealingResult]:
        """
        Heal all failures

        Args:
            failures: List of failures to heal
            dry_run: If True, don't update files
            auto_commit: If True, commit changes to git
            branch_name: Optional git branch name

        Returns:
            List of healing results
        """
        results = []

        for failure in failures:
            result = self.heal_failure(failure, dry_run=dry_run)
            results.append(result)

        # Commit if requested
        if auto_commit and not dry_run:
            successful = [r for r in results if r.success and r.update_result]
            if successful:
                self._commit_healings(successful, branch_name)

        return results

    def _commit_healings(
            self,
            results: List[HealingResult],
            branch_name: Optional[str]
    ):
        """Commit healed selectors to git"""
        updated_files = [
            r.update_result.file_path
            for r in results
            if r.update_result
        ]

        healing_details = []
        for r in results:
            if r.update_result and r.best_match:
                healing_details.append({
                    'file_path': r.update_result.file_path,
                    'element_name': r.failure.element_name or 'unknown',
                    'old_selector': r.update_result.old_selector,
                    'new_selector': r.update_result.new_selector,
                    'confidence': r.best_match.combined_confidence,
                    'strategy': r.best_match.selector.strategy.value
                })

        # Commit
        commit_info = self.git_integration.commit_healing(
            updated_files,
            healing_details,
            branch_name
        )

        if commit_info:
            print(f"\nCommitted: {commit_info.commit_hash[:8]}")
            print(f"Files: {len(commit_info.files_changed)}")
            print(f"Selectors: {commit_info.selectors_healed}")

        # Save metadata
        self.git_integration.save_healing_metadata(healing_details)

    def generate_report(
            self,
            results: List[HealingResult]
    ) -> str:
        """Generate comprehensive healing report"""
        total = len(results)
        successful = len([r for r in results if r.success])

        report = ["=" * 80]
        report.append("HEALING REPORT")
        report.append("=" * 80)
        report.append("")
        report.append(f"Total failures: {total}")
        report.append(f"Successfully healed: {successful} ({successful / total * 100:.1f}%)")
        report.append(f"Failed to heal: {total - successful}")
        report.append("")
        report.append("=" * 80)
        report.append("")

        # Successful healings
        if successful:
            report.append("SUCCESSFUL HEALINGS:")
            report.append("")

            for i, r in enumerate([r for r in results if r.success], 1):
                report.append(f"{i}. {r.failure.test_name}")
                report.append(f"   Element: {r.failure.element_name or 'unknown'}")
                report.append(f"   Old: {r.failure.selector_tuple}")

                if r.best_match:
                    report.append(f"   New: {r.best_match.selector.selector_tuple}")
                    report.append(f"   Confidence: {r.best_match.combined_confidence:.2f}")
                    report.append(f"   Strategy: {r.best_match.selector.strategy.value}")

                if r.update_result:
                    report.append(f"   File: {r.update_result.file_path}")

                report.append("")

        # Failed healings
        failed = [r for r in results if not r.success]
        if failed:
            report.append("FAILED HEALINGS:")
            report.append("")

            for i, r in enumerate(failed, 1):
                report.append(f"{i}. {r.failure.test_name}")
                report.append(f"   Element: {r.failure.element_name or 'unknown'}")
                report.append(f"   Selector: {r.failure.selector_tuple}")
                report.append(f"   Reason: {r.error_message}")
                report.append("")

        report.append("=" * 80)

        return "\n".join(report)
