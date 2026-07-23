"""Fallback-usage tracking and Page Object auto-update.

Extracted from SelectorHealer as its own responsibility: record when a Page
Object's fallback selector rescued a lookup, and — once a fallback proves
itself repeatedly — promote it to the primary selector in the Page Object file.
SelectorHealer inherits this, so the public API is unchanged.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class FallbackTracker:
    """Tracks fallback-selector usage and auto-updates Page Objects."""

    def __init__(self) -> None:
        """Initialize the fallback report / page-object update history."""
        self.fallback_reports: List[Dict[str, Any]] = []
        self.page_object_updates: List[Dict[str, Any]] = []

    def report_fallback_usage(
        self,
        element_name: str,
        page_object_file: str,
        primary_selector: str,
        successful_fallback: str,
        fallback_index: int,
        platform: str,
    ) -> None:
        """
        Report that a fallback selector was used successfully.

        This is called from Page Object _find_element_with_fallback() method
        when a fallback selector succeeds after primary fails.

        Args:
            element_name: Name of the element (e.g., 'login_button')
            page_object_file: Path to Page Object file
            primary_selector: The selector that failed
            successful_fallback: The fallback selector that succeeded
            fallback_index: Index of fallback (0-based)
            platform: 'android' or 'ios'
        """
        report = {
            "timestamp": self._get_timestamp(),
            "element_name": element_name,
            "page_object_file": page_object_file,
            "primary_selector": primary_selector,
            "successful_fallback": successful_fallback,
            "fallback_index": fallback_index,
            "platform": platform,
        }

        self.fallback_reports.append(report)

        logger.info(
            f"[SelectorHealer] Fallback reported: {element_name} in {page_object_file}\n"
            f"  Failed: {primary_selector}\n"
            f"  Succeeded: {successful_fallback} (fallback #{fallback_index + 1})"
        )

        # Auto-update Page Object if threshold reached
        if self._should_auto_update(element_name, page_object_file):
            self.update_page_object(page_object_file, element_name, successful_fallback, platform)

    def _should_auto_update(self, element_name: str, page_object_file: str) -> bool:
        """
        Determine if Page Object should be auto-updated.

        Auto-update if:
        - Same element failed 3+ times
        - Same fallback succeeded 3+ times
        """
        # Count failures for this element in this file
        failures = [
            r
            for r in self.fallback_reports
            if r["element_name"] == element_name and r["page_object_file"] == page_object_file
        ]

        if len(failures) < 3:
            return False

        # Check if same fallback succeeded multiple times
        recent_failures = failures[-5:]  # Last 5 failures
        fallback_counts: Dict[str, int] = {}

        for failure in recent_failures:
            fallback = failure["successful_fallback"]
            fallback_counts[fallback] = fallback_counts.get(fallback, 0) + 1

        # If any fallback succeeded 3+ times, auto-update
        return any(count >= 3 for count in fallback_counts.values())

    def update_page_object(
        self, page_object_file: str, element_name: str, new_primary_selector: str, platform: str
    ) -> bool:
        """
        Update Page Object file with new primary selector.

        Args:
            page_object_file: Path to Page Object file
            element_name: Element to update
            new_primary_selector: New selector to promote to primary
            platform: 'android' or 'ios'

        Returns:
            True if update successful
        """
        from pathlib import Path
        import re

        page_path = Path(page_object_file)

        if not page_path.exists():
            logger.error(f"[SelectorHealer] Page Object not found: {page_object_file}")
            return False

        try:
            # Read current Page Object
            content = page_path.read_text()

            # Find selector dictionary for this element
            selector_name = f"{element_name.upper()}_SELECTOR"

            # Pattern to match selector dictionary
            pattern = rf'({selector_name}\s*=\s*\{{[^}}]+"{platform}"\s*:\s*)"([^"]+)"'

            # Replace with new selector
            def replace_selector(match: Any) -> str:
                prefix = match.group(1)
                old_selector = match.group(2)

                logger.info(
                    f"[SelectorHealer] Updating {element_name} in {page_object_file}\n"
                    f"  Old ({platform}): {old_selector}\n"
                    f"  New ({platform}): {new_primary_selector}"
                )

                return f'{prefix}"{new_primary_selector}"'

            updated_content = re.sub(pattern, replace_selector, content, count=1)

            if updated_content == content:
                logger.warning(f"[SelectorHealer] Selector not found for update: {selector_name} ({platform})")
                return False

            # Backup original file
            backup_path = page_path.with_suffix(".py.bak")
            page_path.rename(backup_path)

            # Write updated content
            page_path.write_text(updated_content)

            # Record update
            update_record = {
                "timestamp": self._get_timestamp(),
                "page_object_file": page_object_file,
                "element_name": element_name,
                "platform": platform,
                "new_primary_selector": new_primary_selector,
                "backup_file": str(backup_path),
            }

            self.page_object_updates.append(update_record)

            logger.info(
                "[SelectorHealer] Page Object updated successfully!\n"
                f"  File: {page_object_file}\n"
                f"  Element: {element_name}\n"
                f"  Platform: {platform}\n"
                f"  New selector: {new_primary_selector}\n"
                f"  Backup: {backup_path}"
            )

            return True

        except (OSError, re.error, UnicodeDecodeError, ValueError) as e:
            logger.error(f"[SelectorHealer] Failed to update Page Object: {e}")
            return False

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime

        return datetime.now().isoformat()

    def get_fallback_stats(self) -> Dict[str, Any]:
        """Get statistics about fallback usage."""
        if not self.fallback_reports:
            return {
                "total_fallbacks": 0,
                "unique_elements": 0,
                "unique_page_objects": 0,
                "auto_updates": len(self.page_object_updates),
                "by_platform": {},
            }

        # Count unique elements and files
        unique_elements = set(r["element_name"] for r in self.fallback_reports)
        unique_files = set(r["page_object_file"] for r in self.fallback_reports)

        # Count by platform
        by_platform = {}
        for report in self.fallback_reports:
            platform = report["platform"]
            if platform not in by_platform:
                by_platform[platform] = 0
            by_platform[platform] += 1

        return {
            "total_fallbacks": len(self.fallback_reports),
            "unique_elements": len(unique_elements),
            "unique_page_objects": len(unique_files),
            "auto_updates": len(self.page_object_updates),
            "by_platform": by_platform,
        }
