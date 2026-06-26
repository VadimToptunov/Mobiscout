"""
Doctor Command - System Health Checks

Comprehensive health check for the framework and environment.
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.table import Table


class CheckStatus(Enum):
    """Status of a health check"""
    PASS = "✓"
    FAIL = "✗"
    WARN = "⚠"
    SKIP = "○"


@dataclass
class HealthCheck:
    """Result of a single health check"""
    name: str
    status: CheckStatus
    message: str
    fix_command: Optional[str] = None


class SystemDoctor:
    """
    Comprehensive system health checker
    
    Verifies:
    - Python version
    - Required packages
    - Git configuration
    - Device connectivity
    - File permissions
    - Performance
    """

    def __init__(self, console: Console):
        self.console = console
        self.checks: List[HealthCheck] = []

    def run_all_checks(self, verbose: bool = False) -> List[HealthCheck]:
        """Run all health checks"""
        checks_to_run = [
            ("Python Environment", self._check_python),
            ("Required Packages", self._check_packages),
            ("Git Configuration", self._check_git),
            ("File Permissions", self._check_permissions),
            ("Appium Server", self._check_appium),
            ("Connected Devices", self._check_devices),
            ("Configuration Files", self._check_config),
            ("Performance", self._check_performance),
        ]

        for name, check_func in track(checks_to_run, description="Running checks..."):
            try:
                result = check_func(verbose)
                self.checks.append(result)
            except (OSError, subprocess.SubprocessError, ImportError, RuntimeError) as e:
                self.checks.append(
                    HealthCheck(
                        name=name,
                        status=CheckStatus.FAIL,
                        message=f"Check failed: {e}",
                    )
                )

        return self.checks

    def _check_python(self, verbose: bool) -> HealthCheck:
        """Check Python version and environment"""
        version = sys.version_info

        if version >= (3, 9):
            return HealthCheck(
                name="Python Version",
                status=CheckStatus.PASS,
                message=f"Python {version.major}.{version.minor}.{version.micro}",
            )
        elif version >= (3, 7):
            return HealthCheck(
                name="Python Version",
                status=CheckStatus.WARN,
                message=f"Python {version.major}.{version.minor} (3.9+ recommended)",
            )
        else:
            return HealthCheck(
                name="Python Version",
                status=CheckStatus.FAIL,
                message=f"Python {version.major}.{version.minor} (3.9+ required)",
                fix_command="Install Python 3.9+",
            )

    def _check_packages(self, verbose: bool) -> HealthCheck:
        """Check required packages"""
        required = [
            "click",
            "rich",
            "pydantic",
            "pytest",
            "requests",
            "pyyaml",
        ]

        missing = []
        for package in required:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)

        if not missing:
            return HealthCheck(
                name="Required Packages",
                status=CheckStatus.PASS,
                message=f"All {len(required)} packages installed",
            )
        else:
            return HealthCheck(
                name="Required Packages",
                status=CheckStatus.FAIL,
                message=f"Missing: {', '.join(missing)}",
                fix_command=f"pip install {' '.join(missing)}",
            )

    def _check_git(self, verbose: bool) -> HealthCheck:
        """Check Git configuration"""
        git_path = shutil.which("git")

        if not git_path:
            return HealthCheck(
                name="Git",
                status=CheckStatus.FAIL,
                message="Git not found in PATH",
                fix_command="Install Git",
            )

        try:
            result = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                return HealthCheck(
                    name="Git",
                    status=CheckStatus.PASS,
                    message=f"Configured for {result.stdout.strip()}",
                )
            else:
                return HealthCheck(
                    name="Git",
                    status=CheckStatus.WARN,
                    message="Git not configured",
                    fix_command='git config --global user.name "Your Name"',
                )
        except (subprocess.SubprocessError, OSError) as e:
            return HealthCheck(
                name="Git",
                status=CheckStatus.WARN,
                message=f"Could not check: {e}",
            )

    def _check_permissions(self, verbose: bool) -> HealthCheck:
        """Check file system permissions"""
        test_dir = Path(".")

        # Check write permission
        try:
            test_file = test_dir / ".doctor_test"
            test_file.write_text("test")
            test_file.unlink()

            return HealthCheck(
                name="File Permissions",
                status=CheckStatus.PASS,
                message="Write permission OK",
            )
        except PermissionError:
            return HealthCheck(
                name="File Permissions",
                status=CheckStatus.FAIL,
                message="No write permission in current directory",
            )

    def _check_appium(self, verbose: bool) -> HealthCheck:
        """Check Appium server availability"""
        appium_path = shutil.which("appium")

        if not appium_path:
            return HealthCheck(
                name="Appium",
                status=CheckStatus.WARN,
                message="Appium not found (optional)",
                fix_command="npm install -g appium",
            )

        try:
            result = subprocess.run(
                ["appium", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                version = result.stdout.strip()
                return HealthCheck(
                    name="Appium",
                    status=CheckStatus.PASS,
                    message=f"Appium {version}",
                )
        except (subprocess.SubprocessError, OSError):
            pass

        return HealthCheck(
            name="Appium",
            status=CheckStatus.WARN,
            message="Could not verify Appium",
        )

    def _check_devices(self, verbose: bool) -> HealthCheck:
        """Check connected devices"""
        try:
            from framework.devices.device_manager import DeviceManager

            manager = DeviceManager()
            devices = manager.get_available_devices()

            if devices and len(devices) > 0:
                return HealthCheck(
                    name="Devices",
                    status=CheckStatus.PASS,
                    message=f"{len(devices)} device(s) available",
                )
            else:
                return HealthCheck(
                    name="Devices",
                    status=CheckStatus.WARN,
                    message="No devices found",
                )
        except (ImportError, OSError, RuntimeError) as e:
            return HealthCheck(
                name="Devices",
                status=CheckStatus.SKIP,
                message=f"Could not check: {e}",
            )

    def _check_config(self, verbose: bool) -> HealthCheck:
        """Check configuration files"""
        config_files = [
            Path("pyproject.toml"),
            Path("requirements.txt"),
        ]

        missing = [f for f in config_files if not f.exists()]

        if not missing:
            return HealthCheck(
                name="Configuration",
                status=CheckStatus.PASS,
                message="All config files present",
            )
        elif len(missing) < len(config_files):
            return HealthCheck(
                name="Configuration",
                status=CheckStatus.WARN,
                message=f"Missing: {', '.join(str(f) for f in missing)}",
            )
        else:
            return HealthCheck(
                name="Configuration",
                status=CheckStatus.FAIL,
                message="Configuration files not found",
            )

    def _check_performance(self, verbose: bool) -> HealthCheck:
        """Basic performance check"""
        import time

        # Simple benchmark: file I/O
        start = time.time()
        test_file = Path(".doctor_bench")

        try:
            for _ in range(100):
                test_file.write_text("benchmark")
                test_file.read_text()

            test_file.unlink()
            duration = time.time() - start

            if duration < 0.5:
                return HealthCheck(
                    name="Performance",
                    status=CheckStatus.PASS,
                    message=f"I/O performance good ({duration * 1000:.0f}ms)",
                )
            else:
                return HealthCheck(
                    name="Performance",
                    status=CheckStatus.WARN,
                    message=f"Slow I/O ({duration * 1000:.0f}ms)",
                )
        except (OSError, PermissionError) as e:
            return HealthCheck(
                name="Performance",
                status=CheckStatus.SKIP,
                message=f"Could not benchmark: {e}",
            )

    def generate_report(self) -> Tuple[int, int, int, int]:
        """Generate health report statistics"""
        passed = sum(1 for c in self.checks if c.status == CheckStatus.PASS)
        failed = sum(1 for c in self.checks if c.status == CheckStatus.FAIL)
        warned = sum(1 for c in self.checks if c.status == CheckStatus.WARN)
        skipped = sum(1 for c in self.checks if c.status == CheckStatus.SKIP)

        return passed, failed, warned, skipped

    def print_report(self, verbose: bool = False) -> None:
        """Print formatted health report"""
        table = Table(title="System Health Check")
        table.add_column("Check", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Details")

        for check in self.checks:
            status_style = {
                CheckStatus.PASS: "green",
                CheckStatus.FAIL: "red",
                CheckStatus.WARN: "yellow",
                CheckStatus.SKIP: "dim",
            }[check.status]

            table.add_row(
                check.name,
                f"[{status_style}]{check.status.value}[/{status_style}]",
                check.message,
            )

        self.console.print(table)

        # Show fix commands
        fixes = [c for c in self.checks if c.fix_command]
        if fixes:
            self.console.print("\n[bold yellow]Suggested Fixes:[/bold yellow]")
            for check in fixes:
                self.console.print(f"  • {check.name}: [cyan]{check.fix_command}[/cyan]")

        # Summary
        passed, failed, warned, skipped = self.generate_report()
        total = len(self.checks)

        if failed > 0:
            style = "red"
            icon = "❌"
        elif warned > 0:
            style = "yellow"
            icon = "⚠️"
        else:
            style = "green"
            icon = "✅"

        summary = (
            f"[{style}]{icon} {passed}/{total} checks passed[/{style}]\n"
            f"[dim]Failed: {failed}, Warnings: {warned}, Skipped: {skipped}[/dim]"
        )

        self.console.print(Panel(summary, title="Summary", border_style=style))
