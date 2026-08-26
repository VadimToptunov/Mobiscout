"""
Doctor Command - System Health Checks

Comprehensive health check for the framework and environment.
"""

import os
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

# Where the framework itself lives (…/framework/health/doctor.py -> repo root), so
# the config check looks at *our* files instead of whatever is in the user's CWD.
_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]


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

    def __init__(self, console: Console) -> None:
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
            ("Appium Driver Manager", self._check_driver_manager),
            ("Android SDK", self._check_android_sdk),
            ("Connected Devices", self._check_devices),
            ("Configuration Files", self._check_config),
            ("Native Core", self._check_native_core),
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

    def _check_native_core(self, verbose: bool) -> HealthCheck:
        """Report the active SAST/complexity backend: the Rust core (with version) or the
        Python fallback (correct but slower — and the signal that a stale/absent wheel is
        silently costing the acceleration)."""
        from framework.analyzers.native import backend_name, native_version

        if backend_name() == "rust":
            return HealthCheck(
                name="Native Core",
                status=CheckStatus.PASS,
                message=f"Rust acceleration active (mobiscout_core {native_version()})",
            )
        return HealthCheck(
            name="Native Core",
            status=CheckStatus.WARN,
            message="Python fallback — the Rust core is not installed or too old for this ABI",
            fix_command="cd rust_core && maturin develop",
        )

    def _check_packages(self, verbose: bool) -> HealthCheck:
        """Check required packages"""
        # Map pip distribution name -> importable module name (they differ, e.g. pyyaml -> yaml).
        required = {
            "click": "click",
            "rich": "rich",
            "pydantic": "pydantic",
            "pytest": "pytest",
            "requests": "requests",
            "pyyaml": "yaml",
        }

        missing = []
        for package, import_name in required.items():
            try:
                __import__(import_name)
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
                # text=True alone decodes with the locale codepage on Windows,
                # where a non-ASCII user.name raises UnicodeDecodeError.
                encoding="utf-8",
                errors="replace",
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
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )

            if result.returncode == 0:
                version = result.stdout.strip()
                from framework.health.preflight import installed_appium_drivers

                drivers = installed_appium_drivers()
                missing = [d for d in ("uiautomator2", "xcuitest") if d not in drivers]
                if missing:
                    return HealthCheck(
                        name="Appium",
                        status=CheckStatus.WARN,
                        message=f"Appium {version}; missing driver(s): {', '.join(missing)}",
                        fix_command=f"appium driver install {missing[0]}",
                    )
                return HealthCheck(
                    name="Appium",
                    status=CheckStatus.PASS,
                    message=f"Appium {version} (drivers: {', '.join(sorted(drivers))})",
                )
        except (subprocess.SubprocessError, OSError):
            pass

        return HealthCheck(
            name="Appium",
            status=CheckStatus.WARN,
            message="Could not verify Appium",
        )

    def _check_driver_manager(self, verbose: bool) -> HealthCheck:
        """Diagnose the npm >= 11 breakage of Appium's in-place ``driver update``.

        Appium's in-place update shells out to ``npm install --global-style`` over
        the existing driver tree; on npm >= 11 (bundled with Node >= 23) npm
        mishandles that and it dies with ``Cannot read properties of null (reading
        'package')``. A fresh install is unaffected, so the fix is to reinstall the
        driver (uninstall + install) — no Node/npm change. We diagnose purely from
        ``node``/``npm --version``; we never run the failing update ourselves.

        PASS when node/npm are absent (can't diagnose, and drivers may already be
        installed) or healthy (npm <= 10). WARN — not FAIL, since installed drivers
        keep working and reinstall updates cleanly — when npm >= 11, with the
        reinstall remediation as fix_command.
        """
        from framework.health.preflight import (
            driver_manager_healthy,
            driver_manager_remediation,
            node_npm_versions,
        )

        node, npm = node_npm_versions()
        ok, reason = driver_manager_healthy(lambda: (node, npm))
        if ok:
            if node is None and npm is None:
                return HealthCheck(
                    name="Appium Driver Manager",
                    status=CheckStatus.PASS,
                    message="node/npm not found; nothing to diagnose",
                )
            return HealthCheck(
                name="Appium Driver Manager",
                status=CheckStatus.PASS,
                message=f"npm {npm or '?'} (Node {node or '?'}) supports Appium driver install",
            )

        return HealthCheck(
            name="Appium Driver Manager",
            status=CheckStatus.WARN,
            message=reason or driver_manager_remediation(node, npm),
            fix_command=driver_manager_remediation(node, npm),
        )

    def _check_android_sdk(self, verbose: bool) -> HealthCheck:
        """Check that an Android SDK is available (needed by Appium/UiAutomator2).

        PASS when ``ANDROID_HOME``/``ANDROID_SDK_ROOT`` points at a real SDK; WARN
        (with an ``export`` fix) when an SDK is detected on disk but the env var is
        unset or points at a directory with no ``platform-tools/adb``; FAIL when no
        SDK can be found at all. ``resolve_android_home`` only ever returns a path
        that holds an adb, so a set-but-broken var never passes — it looks
        configured while UiAutomator2 dies on it.
        """
        from framework.health.preflight import resolve_android_home

        existing = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        detected = resolve_android_home()
        if existing and detected == existing:
            return HealthCheck(
                name="Android SDK",
                status=CheckStatus.PASS,
                message=f"ANDROID_HOME={existing}",
            )

        if detected:
            unset = f"SDK detected but ANDROID_HOME unset: {detected}"
            broken = f"ANDROID_HOME={existing} has no platform-tools/adb; SDK detected at {detected}"
            return HealthCheck(
                name="Android SDK",
                status=CheckStatus.WARN,
                message=broken if existing else unset,
                fix_command=f"export ANDROID_HOME={detected}",
            )

        if existing:
            return HealthCheck(
                name="Android SDK",
                status=CheckStatus.FAIL,
                message=f"ANDROID_HOME={existing} has no platform-tools/adb, and no SDK was found elsewhere",
                fix_command="Point ANDROID_HOME at a real Android SDK (the directory holding platform-tools/adb)",
            )

        return HealthCheck(
            name="Android SDK",
            status=CheckStatus.FAIL,
            message="No Android SDK found",
            fix_command="Install the Android SDK and set ANDROID_HOME",
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
        """Check the framework's own configuration files.

        Anchored to where the framework is installed, not the current directory: a
        user running ``mobiscout doctor`` inside their own project has none of our
        files there, and the CWD-relative check turned their whole report red for a
        condition that is meaningless outside this repo. An installed or frozen
        engine ships neither file, so their absence is SKIP, never FAIL.
        """
        config_files = [
            _FRAMEWORK_ROOT / "pyproject.toml",
            _FRAMEWORK_ROOT / "requirements.txt",
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
                message=f"Missing: {', '.join(f.name for f in missing)}",
            )
        else:
            return HealthCheck(
                name="Configuration",
                status=CheckStatus.SKIP,
                message=f"No framework config files at {_FRAMEWORK_ROOT} (not a source checkout)",
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
                test_file.read_text(encoding="utf-8")

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
