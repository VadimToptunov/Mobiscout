"""
Change analyzer for detecting modified files

Analyzes git changes to identify modified files and their impact.
"""

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Set, Optional


class ChangeType(Enum):
    """Type of file change"""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass
class FileChange:
    """Represents a file change"""
    path: Path
    change_type: ChangeType
    old_path: Optional[Path] = None  # For renamed files
    lines_added: int = 0
    lines_deleted: int = 0


class ChangeAnalyzer:
    """
    Analyzes code changes to identify affected files
    """

    def __init__(self, repo_path: Path):
        """
        Initialize change analyzer

        Args:
            repo_path: Path to git repository
        """
        self.repo_path = repo_path

    def get_changes(
            self,
            base_branch: str = "main",
            target_branch: str = "HEAD",
            include_untracked: bool = False
    ) -> List[FileChange]:
        """
        Get list of changed files

        Args:
            base_branch: Base branch to compare against
            target_branch: Target branch/commit
            include_untracked: Include untracked files

        Returns:
            List of file changes
        """
        changes = []

        try:
            # Get diff with base branch
            result = subprocess.run(
                ["git", "dif", "--name-status", f"{base_branch}...{target_branch}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )

            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                parts = line.split('\t')
                status = parts[0]

                if status.startswith('M'):
                    # Modified
                    file_path = Path(parts[1])
                    stats = self._get_file_stats(file_path, base_branch, target_branch)
                    changes.append(FileChange(
                        path=file_path,
                        change_type=ChangeType.MODIFIED,
                        lines_added=stats['added'],
                        lines_deleted=stats['deleted']
                    ))
                elif status.startswith('A'):
                    # Added
                    file_path = Path(parts[1])
                    changes.append(FileChange(
                        path=file_path,
                        change_type=ChangeType.ADDED
                    ))
                elif status.startswith('D'):
                    # Deleted
                    file_path = Path(parts[1])
                    changes.append(FileChange(
                        path=file_path,
                        change_type=ChangeType.DELETED
                    ))
                elif status.startswith('R'):
                    # Renamed
                    old_path = Path(parts[1])
                    new_path = Path(parts[2])
                    changes.append(FileChange(
                        path=new_path,
                        change_type=ChangeType.RENAMED,
                        old_path=old_path
                    ))

            # Include staged changes
            if target_branch == "HEAD":
                staged = self._get_staged_changes()
                changes.extend(staged)

            # Include untracked files if requested
            if include_untracked:
                untracked = self._get_untracked_files()
                changes.extend(untracked)

        except subprocess.CalledProcessError as e:
            print(f"Warning: Git command failed: {e}")

        return changes

    def get_changed_files(
            self,
            base_branch: str = "main",
            target_branch: str = "HEAD",
            since_commit: Optional[str] = None
    ) -> List[Path]:
        """
        Get list of changed file paths (simplified interface)

        Args:
            base_branch: Base branch to compare against
            target_branch: Target branch/commit
            since_commit: Optional commit to compare since (overrides base_branch if provided)

        Returns:
            List of changed file paths
        """
        if since_commit:
            base_branch = since_commit
        changes = self.get_changes(base_branch, target_branch)
        return [change.path for change in changes]

    def _get_file_stats(
            self,
            file_path: Path,
            base_branch: str,
            target_branch: str
    ) -> dict:
        """Get added/deleted line counts for a file"""
        try:
            result = subprocess.run(
                ["git", "dif", "--numstat", f"{base_branch}...{target_branch}", "--", str(file_path)],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )

            if result.stdout.strip():
                parts = result.stdout.strip().split('\t')
                return {
                    'added': int(parts[0]) if parts[0] != '-' else 0,
                    'deleted': int(parts[1]) if parts[1] != '-' else 0
                }
        except (subprocess.SubprocessError, OSError, ValueError):
            pass

        return {'added': 0, 'deleted': 0}

    def _get_staged_changes(self) -> List[FileChange]:
        """Get staged changes"""
        changes = []

        try:
            result = subprocess.run(
                ["git", "dif", "--cached", "--name-status"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )

            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                parts = line.split('\t')
                status = parts[0]

                if status.startswith('M'):
                    changes.append(FileChange(
                        path=Path(parts[1]),
                        change_type=ChangeType.MODIFIED
                    ))
                elif status.startswith('A'):
                    changes.append(FileChange(
                        path=Path(parts[1]),
                        change_type=ChangeType.ADDED
                    ))
                elif status.startswith('D'):
                    changes.append(FileChange(
                        path=Path(parts[1]),
                        change_type=ChangeType.DELETED
                    ))
        except (subprocess.SubprocessError, OSError):
            pass

        return changes

    def _get_untracked_files(self) -> List[FileChange]:
        """Get untracked files"""
        changes = []

        try:
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )

            for line in result.stdout.strip().split('\n'):
                if line:
                    changes.append(FileChange(
                        path=Path(line),
                        change_type=ChangeType.ADDED
                    ))
        except (subprocess.SubprocessError, OSError):
            pass

        return changes

    def get_changed_directories(self, changes: List[FileChange]) -> Set[Path]:
        """Get set of directories containing changes"""
        directories = set()
        for change in changes:
            if change.change_type != ChangeType.DELETED:
                directories.add(change.path.parent)
        return directories

    def filter_by_extension(
            self,
            changes: List[FileChange],
            extensions: List[str]
    ) -> List[FileChange]:
        """
        Filter changes by file extension

        Args:
            changes: List of changes
            extensions: List of extensions (e.g., ['.py', '.kt', '.swift'])

        Returns:
            Filtered changes
        """
        return [
            change for change in changes
            if change.path.suffix in extensions
        ]
