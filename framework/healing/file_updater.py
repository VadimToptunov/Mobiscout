"""
File updater

Updates Page Object files with healed selectors.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List


@dataclass
class UpdateResult:
    """Result of file update operation"""
    success: bool
    file_path: Path
    old_selector: tuple
    new_selector: tuple
    backup_path: Optional[Path] = None
    error_message: Optional[str] = None

    def __repr__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.file_path}: {self.old_selector} → {self.new_selector}"


class FileUpdater:
    """
    Updates Page Object files with healed selectors
    """

    def __init__(self, create_backup: bool = True):
        """
        Initialize file updater

        Args:
            create_backup: Whether to create backup files before updating
        """
        self.create_backup = create_backup

    def update_selector(
            self,
            file_path: Path,
            element_name: str,
            old_selector: tuple,
            new_selector: tuple,
            confidence: float
    ) -> UpdateResult:
        """
        Update selector in Page Object file

        Args:
            file_path: Path to Page Object file
            element_name: Name of element/locator
            old_selector: Old (type, value) tuple
            new_selector: New (type, value) tuple
            confidence: Confidence score for the healing

        Returns:
            UpdateResult with operation details
        """
        if not file_path.exists():
            return UpdateResult(
                success=False,
                file_path=file_path,
                old_selector=old_selector,
                new_selector=new_selector,
                error_message="File not found"
            )

        # Determine file type and use appropriate updater
        if file_path.suffix == '.py':
            return self._update_python_file(
                file_path, element_name, old_selector, new_selector, confidence
            )
        elif file_path.suffix == '.kt':
            return self._update_kotlin_file(
                file_path, element_name, old_selector, new_selector, confidence
            )
        elif file_path.suffix == '.swift':
            return self._update_swift_file(
                file_path, element_name, old_selector, new_selector, confidence
            )
        else:
            return UpdateResult(
                success=False,
                file_path=file_path,
                old_selector=old_selector,
                new_selector=new_selector,
                error_message=f"Unsupported file type: {file_path.suffix}"
            )

    def _update_python_file(
            self,
            file_path: Path,
            element_name: str,
            old_selector: tuple,
            new_selector: tuple,
            confidence: float
    ) -> UpdateResult:
        """Update Python Page Object file"""
        try:
            content = file_path.read_text()

            # Create backup
            backup_path = None
            if self.create_backup:
                backup_path = file_path.with_suffix(f'.py.bak.{int(datetime.now().timestamp())}')
                backup_path.write_text(content)

            # Find and replace selector
            # Pattern: element_name = ("type", "value")
            # Escape all user-controlled parts to prevent regex injection
            old_pattern = f'{re.escape(element_name)}\\s*=\\s*\\(\\s*["\']({re.escape(old_selector[0])})["\']\\s*,\\s*["\']({re.escape(old_selector[1])})["\']\\s*\\)'

            match = re.search(old_pattern, content)
            if not match:
                return UpdateResult(
                    success=False,
                    file_path=file_path,
                    old_selector=old_selector,
                    new_selector=new_selector,
                    error_message=f"Selector pattern not found: {element_name}"
                )

            # Generate healing comment
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            comment = (
                f"    # Auto-healed: {timestamp}\n"
                f"    # Original: {old_selector} - element not found\n"
                f"    # New: {new_selector[0]} strategy, confidence: {confidence:.2f}\n"
            )

            # Build new selector line
            new_line = f'{element_name} = ("{new_selector[0]}", "{new_selector[1]}")'

            # Replace with commented version
            replacement = f'{comment}    {new_line}\n    # Fallback: {old_selector}'

            new_content = re.sub(old_pattern, replacement, content)

            # Write updated content
            file_path.write_text(new_content)

            return UpdateResult(
                success=True,
                file_path=file_path,
                old_selector=old_selector,
                new_selector=new_selector,
                backup_path=backup_path
            )

        except (OSError, re.error, UnicodeDecodeError) as e:
            return UpdateResult(
                success=False,
                file_path=file_path,
                old_selector=old_selector,
                new_selector=new_selector,
                error_message=str(e)
            )

    def _update_kotlin_file(
            self,
            file_path: Path,
            element_name: str,
            old_selector: tuple,
            new_selector: tuple,
            confidence: float
    ) -> UpdateResult:
        """Update Kotlin Page Object file"""
        try:
            content = file_path.read_text()

            # Create backup
            backup_path = None
            if self.create_backup:
                backup_path = file_path.with_suffix(f'.kt.bak.{int(datetime.now().timestamp())}')
                backup_path.write_text(content)

            # Kotlin pattern: val elementName = By.id("value") or MobileBy.AndroidUIAutomator("...")
            # This is simplified - real implementation would handle more patterns
            # Escape element_name to prevent regex injection
            old_pattern = f'val\\s+{re.escape(element_name)}\\s*=\\s*.*?"{re.escape(old_selector[1])}"'

            match = re.search(old_pattern, content)
            if not match:
                return UpdateResult(
                    success=False,
                    file_path=file_path,
                    old_selector=old_selector,
                    new_selector=new_selector,
                    error_message=f"Selector pattern not found: {element_name}"
                )

            # Generate healing comment
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            comment = (
                f"    // Auto-healed: {timestamp}\n"
                f"    // Original: {old_selector} - element not found\n"
                f"    // New: {new_selector[0]} strategy, confidence: {confidence:.2f}\n"
            )

            # Build new selector (simplified)
            strategy_map = {
                'id': f'By.id("{new_selector[1]}")',
                'xpath': f'By.xpath("{new_selector[1]}")',
                'accessibility_id': f'MobileBy.AccessibilityId("{new_selector[1]}")'
            }
            by_method = strategy_map.get(new_selector[0], f'By.xpath("{new_selector[1]}")')

            new_line = f'val {element_name} = {by_method}'

            # Replace
            replacement = f'{comment}    {new_line}'
            new_content = re.sub(old_pattern, replacement, content)

            file_path.write_text(new_content)

            return UpdateResult(
                success=True,
                file_path=file_path,
                old_selector=old_selector,
                new_selector=new_selector,
                backup_path=backup_path
            )

        except (OSError, re.error, UnicodeDecodeError) as e:
            return UpdateResult(
                success=False,
                file_path=file_path,
                old_selector=old_selector,
                new_selector=new_selector,
                error_message=str(e)
            )

    def _update_swift_file(
            self,
            file_path: Path,
            element_name: str,
            old_selector: tuple,
            new_selector: tuple,
            confidence: float
    ) -> UpdateResult:
        """Update Swift Page Object file"""
        try:
            content = file_path.read_text()

            # Create backup
            backup_path = None
            if self.create_backup:
                backup_path = file_path.with_suffix(f'.swift.bak.{int(datetime.now().timestamp())}')
                backup_path.write_text(content)

            # Swift pattern: var elementName: XCUIElement { app.buttons["value"] }
            # Escape element_name to prevent regex injection
            old_pattern = f'var\\s+{re.escape(element_name)}.*?"{re.escape(old_selector[1])}"'

            match = re.search(old_pattern, content, re.DOTALL)
            if not match:
                return UpdateResult(
                    success=False,
                    file_path=file_path,
                    old_selector=old_selector,
                    new_selector=new_selector,
                    error_message=f"Selector pattern not found: {element_name}"
                )

            # Generate healing comment
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            comment = (
                f"    // Auto-healed: {timestamp}\n"
                f"    // Original: {old_selector} - element not found\n"
                f"    // New: {new_selector[0]} strategy, confidence: {confidence:.2f}\n"
            )

            # Build new selector
            # element_type_map = {  # Unused
            #     'button': 'buttons',
            #     'textfield': 'textFields',
            #     'label': 'staticTexts'
            # }

            # Simplified - use identifier if available
            if new_selector[0] == 'accessibility_id':
                new_line = f'var {element_name}: XCUIElement {{ app.buttons.matching(identifier: "{new_selector[1]}").firstMatch }}'
            else:
                new_line = f'var {element_name}: XCUIElement {{ app.descendants(matching: .any)["{new_selector[1]}"].firstMatch }}'

            # Replace
            replacement = f'{comment}    {new_line}'
            new_content = re.sub(old_pattern, replacement, content, flags=re.DOTALL)

            file_path.write_text(new_content)

            return UpdateResult(
                success=True,
                file_path=file_path,
                old_selector=old_selector,
                new_selector=new_selector,
                backup_path=backup_path
            )

        except (OSError, re.error, UnicodeDecodeError) as e:
            return UpdateResult(
                success=False,
                file_path=file_path,
                old_selector=old_selector,
                new_selector=new_selector,
                error_message=str(e)
            )

    def restore_backup(self, backup_path: Path) -> bool:
        """
        Restore file from backup

        Args:
            backup_path: Path to backup file

        Returns:
            True if restored successfully
        """
        try:
            if not backup_path.exists():
                return False

            # Validate backup path format to prevent path traversal
            backup_str = str(backup_path)
            if '.bak.' not in backup_str:
                print(f"Error: Invalid backup file format: {backup_path}")
                return False

            # Get original file path safely
            original_path = Path(backup_str.split('.bak.')[0])

            # Security check: ensure original path is in same directory as backup
            # to prevent path traversal attacks
            if original_path.parent.resolve() != backup_path.parent.resolve():
                print("Error: Security violation - backup and original not in same directory")
                return False

            # Validate no path traversal in the original path
            if '..' in str(original_path):
                print("Error: Path traversal detected in backup path")
                return False

            # Restore
            content = backup_path.read_text()
            original_path.write_text(content)

            # Delete backup
            backup_path.unlink()

            return True

        except OSError as e:
            print(f"Error restoring backup: {e}")
            return False

    def batch_update(
            self,
            updates: List[tuple]
    ) -> List[UpdateResult]:
        """
        Perform batch updates

        Args:
            updates: List of (file_path, element_name, old_selector, new_selector, confidence) tuples

        Returns:
            List of UpdateResults
        """
        results = []

        for file_path, element_name, old_selector, new_selector, confidence in updates:
            result = self.update_selector(
                file_path, element_name, old_selector, new_selector, confidence
            )
            results.append(result)

        return results
