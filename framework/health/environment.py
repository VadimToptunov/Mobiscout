"""
Environment detection — is this machine ready to automate, and what's missing?

The IDE plugin (and `mobiscout`) needs to know, before offering to crawl: is Appium
installed, which drivers, is the Android SDK (adb) there, Xcode/simctl for iOS,
a JDK for Appium? This probes the toolchain and reports versions + copy-paste
install hints for whatever is missing — the Phase-4 "Environment Intelligence"
the plugin surfaces and the daemon exposes as ``environment/detect``.

The command runner is injectable so the whole thing is unit-testable without the
tools actually installed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from framework.health.preflight import (
    driver_manager_healthy,
    driver_manager_remediation,
    resolve_android_home,
)

Runner = Callable[[List[str]], Tuple[int, str]]

_VERSION = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def _run(cmd: List[str]) -> Tuple[int, str]:
    """Run a command, returning (exit_code, combined_output). 127 if not found."""
    try:
        # text=True alone decodes with the locale codepage on Windows, where the
        # non-ASCII output of these tools raises UnicodeDecodeError; pin UTF-8.
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, ""
    except (OSError, subprocess.SubprocessError):
        return 1, ""


@dataclass
class Tool:
    name: str
    found: bool
    version: str = ""
    hint: str = ""


def _tool_version(cmd: List[str], run: Runner) -> Optional[str]:
    """Return the raw ``--version`` output via the injected runner, or ``None``.

    Non-zero exit (incl. 127 not-found) or empty output yields ``None``. Used to
    probe node/npm for the driver-manager diagnosis through the same testable seam.
    """
    code, out = run(cmd)
    if code != 0:
        return None
    out = (out or "").strip()
    return out or None


def _probe(name: str, cmd: List[str], hint: str, run: Runner) -> Tool:
    code, out = run(cmd)
    # A tool that exits non-zero with nothing to say is not usable: a hung probe
    # (the timeout maps to code 1), a broken shim, or `xcrun simctl` refusing on an
    # unaccepted Xcode license. Reporting those as found makes android_ready /
    # ios_ready claim a toolchain that cannot actually run.
    if code != 0 and not out:
        return Tool(name, False, hint=hint)
    m = _VERSION.search(out)
    return Tool(name, True, version=m.group(1) if m else "")


@dataclass
class Environment:
    tools: List[Tool] = field(default_factory=list)
    appium_drivers: List[str] = field(default_factory=list)
    android_ready: bool = False
    ios_ready: bool = False
    # The resolved Android SDK path (from ANDROID_HOME/ANDROID_SDK_ROOT or a probed
    # common location), or None when no SDK is found on this machine.
    android_home: Optional[str] = None
    # True only when ANDROID_HOME/ANDROID_SDK_ROOT is actually exported in the env
    # — a detected-but-unset SDK is False (an Appium server won't inherit it).
    android_home_set: bool = False
    # The Appium/UiAutomator2 path needs an SDK path *and* the driver, not just adb
    # on PATH — this is the readiness the plugin should gate an Appium session on.
    appium_android_ready: bool = False
    # True when Appium's in-place `driver update` works here — False when npm >= 11
    # (Node >= 23), where it mishandles `--global-style` over the existing driver
    # tree. A fresh install/reinstall is unaffected and installed drivers keep
    # working, so this is a warning (reinstall to update), not a blocker.
    driver_manager_ok: bool = True
    # Copy-paste remediation (reinstall the driver) when driver_manager_ok is False.
    driver_manager_fix: Optional[str] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        # When the SDK is on disk but not exported, hand the plugin a copy-pasteable
        # fix — a separately launched Appium server won't inherit our self-heal.
        if self.android_home is not None and not self.android_home_set:
            data["android_home_fix"] = f"export ANDROID_HOME={self.android_home}"
        return data


def detect_environment(run: Runner = _run) -> Environment:
    """Probe the automation toolchain and report versions + install hints."""
    py = Tool("Python", True, version="{}.{}.{}".format(*sys.version_info[:3]))
    adb = _probe(
        "adb (Android SDK)", ["adb", "version"], "Install Android SDK platform-tools and add adb to PATH.", run
    )
    appium = _probe("Appium", ["appium", "--version"], "npm install -g appium", run)
    java = _probe("Java (JDK)", ["java", "-version"], "Install a JDK 17+ (required by Appium).", run)
    xcode = _probe(
        "Xcode (simctl)", ["xcrun", "simctl", "help"], "Install Xcode + command-line tools (macOS, for iOS).", run
    )

    drivers = []
    if appium.found:
        _, drivers_out = run(["appium", "driver", "list", "--installed"])
        drivers = [d for d in ("uiautomator2", "xcuitest") if d in (drivers_out or "")]

    # ANDROID_HOME matters for the Appium/UiAutomator2 path even when adb is on
    # PATH: probe the SDK path and whether it's actually exported.
    android_home = resolve_android_home()
    android_home_set = bool(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT"))

    # Diagnose the npm >= 11 breakage of `appium driver install/update` from the
    # node/npm versions (probed through the injected runner) — never run the
    # failing update itself.
    node = _tool_version(["node", "--version"], run)
    npm = _tool_version(["npm", "--version"], run)
    driver_manager_ok, _ = driver_manager_healthy(lambda: (node, npm))
    driver_manager_fix = None if driver_manager_ok else driver_manager_remediation(node, npm)

    return Environment(
        tools=[py, adb, appium, java, xcode],
        appium_drivers=drivers,
        # Android crawls over adb directly — no Appium needed.
        android_ready=adb.found,
        # iOS needs an Appium/XCUITest session (server + driver) and Xcode.
        ios_ready=xcode.found and appium.found and "xcuitest" in drivers,
        android_home=android_home,
        android_home_set=android_home_set,
        # The Appium Android path additionally needs the SDK path and the driver.
        appium_android_ready=adb.found and android_home is not None and "uiautomator2" in drivers,
        driver_manager_ok=driver_manager_ok,
        driver_manager_fix=driver_manager_fix,
    )
