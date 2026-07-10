"""
Environment detection — is this machine ready to automate, and what's missing?

The IDE plugin (and `observe`) needs to know, before offering to crawl: is Appium
installed, which drivers, is the Android SDK (adb) there, Xcode/simctl for iOS,
a JDK for Appium? This probes the toolchain and reports versions + copy-paste
install hints for whatever is missing — the Phase-4 "Environment Intelligence"
the plugin surfaces and the daemon exposes as ``environment/detect``.

The command runner is injectable so the whole thing is unit-testable without the
tools actually installed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Tuple

Runner = Callable[[List[str]], Tuple[int, str]]

_VERSION = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def _run(cmd: List[str]) -> Tuple[int, str]:
    """Run a command, returning (exit_code, combined_output). 127 if not found."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
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


def _probe(name: str, cmd: List[str], hint: str, run: Runner) -> Tool:
    code, out = run(cmd)
    if code == 127 and not out:
        return Tool(name, False, hint=hint)
    m = _VERSION.search(out)
    return Tool(name, True, version=m.group(1) if m else "")


@dataclass
class Environment:
    tools: List[Tool] = field(default_factory=list)
    appium_drivers: List[str] = field(default_factory=list)
    android_ready: bool = False
    ios_ready: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


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

    return Environment(
        tools=[py, adb, appium, java, xcode],
        appium_drivers=drivers,
        # Android crawls over adb directly — no Appium needed.
        android_ready=adb.found,
        # iOS needs an Appium/XCUITest session (server + driver) and Xcode.
        ios_ready=xcode.found and appium.found and "xcuitest" in drivers,
    )
