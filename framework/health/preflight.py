"""Pre-crawl environment checks — catch the failures that give cryptic errors.

The most common dead-end when crawling Android over Appium/UiAutomator2 is a
running Appium **server** that has no ``ANDROID_HOME``/``ANDROID_SDK_ROOT`` in its
environment. adb still works (it's on ``PATH``) so the session gets far enough to
fail deep inside UiAutomator2 with an opaque message. We can't change a running
server's env, but we *can* detect the SDK on this machine and turn the dead-end
into an actionable diagnosis.

Everything here is pure and side-effect-free except :func:`ensure_android_home`,
which self-heals *this* process's env (so the adb subprocesses Mobiscout spawns
inherit ``ANDROID_HOME``). The HTTP and subprocess seams are the module-level
``requests`` and ``subprocess`` so tests can stub them without a real Appium/adb.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# Appium's status endpoint returns a short read; keep the timeout tight so a
# preflight never stalls the CLI when the server is unreachable.
_STATUS_TIMEOUT = 3.0
_DRIVER_LIST_TIMEOUT = 20.0

# name@version, e.g. "uiautomator2@2.34.1" in the text form of `driver list`.
_DRIVER_LINE = re.compile(r"([A-Za-z0-9_-]+)@(\d+\.\d+(?:\.\d+)?)")


@dataclass
class PreflightResult:
    """One environment check outcome, phrased for a human.

    Attributes:
        name: Short label for the check (e.g. ``"ANDROID_HOME"``).
        ok: True if the check is not a hard failure (pass or warn).
        level: ``"pass"``, ``"warn"``, or ``"fail"``.
        detail: Human-readable description of what was found.
        fix: A copy-pasteable remedy, empty when nothing to fix.
    """

    name: str
    ok: bool
    level: str
    detail: str
    fix: str = ""


def _has_adb(sdk: Path) -> bool:
    """Return True if ``sdk`` looks like a real SDK (has ``platform-tools/adb``)."""
    tools = sdk / "platform-tools"
    return (tools / "adb").exists() or (tools / "adb.exe").exists()


def _candidate_sdk_dirs() -> List[Path]:
    """Common per-OS install locations for the Android SDK, most-likely first."""
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return [home / "Library" / "Android" / "sdk"]
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else home / "AppData" / "Local"
        return [base / "Android" / "Sdk"]
    return [home / "Android" / "Sdk"]


def resolve_android_home() -> Optional[str]:
    """Find a usable Android SDK path, or ``None``.

    Prefers a valid ``ANDROID_HOME``/``ANDROID_SDK_ROOT`` (set *and* containing a
    ``platform-tools/adb``); otherwise probes the common per-OS SDK locations and
    returns the first that actually holds an adb. Pure — reads env and filesystem
    only, mutates nothing.
    """
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        val = os.environ.get(var)
        if val and _has_adb(Path(val)):
            return val
    for candidate in _candidate_sdk_dirs():
        if _has_adb(candidate):
            return str(candidate)
    return None


def ensure_android_home() -> Optional[str]:
    """Self-heal this process's env with a detected SDK when it's unset.

    If ``ANDROID_HOME``/``ANDROID_SDK_ROOT`` is already set, return it untouched.
    Otherwise, if :func:`resolve_android_home` finds an SDK, set *both* variables
    in ``os.environ`` (so the adb subprocesses Mobiscout spawns inherit them) and
    return the path. Returns ``None`` when nothing is set and nothing is found.
    """
    existing = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if existing:
        return existing
    detected = resolve_android_home()
    if detected:
        os.environ["ANDROID_HOME"] = detected
        os.environ["ANDROID_SDK_ROOT"] = detected
    return detected


def appium_status(server: str) -> Tuple[bool, Optional[str]]:
    """Probe ``<server>/status`` and report ``(reachable, version)``.

    Uses a short timeout and never raises: any connection, HTTP, or parse problem
    is reported as ``(False, None)`` (unreachable) or ``(True, None)`` (reachable
    but version unknown). The version is read from ``value.build.version`` in the
    W3C-style status payload when present.
    """
    url = server.rstrip("/") + "/status"
    try:
        resp = requests.get(url, timeout=_STATUS_TIMEOUT)
    except Exception:
        return False, None
    if resp.status_code != 200:
        return False, None
    try:
        data: Any = resp.json()
    except Exception:
        return True, None
    version: Optional[str] = None
    value = data.get("value") if isinstance(data, dict) else None
    if isinstance(value, dict):
        build = value.get("build")
        if isinstance(build, dict) and isinstance(build.get("version"), str):
            version = build["version"]
    return True, version


def _parse_driver_list(out: str) -> Dict[str, str]:
    """Parse ``appium driver list --installed`` output (JSON or text) to name->version."""
    out = out.strip()
    if not out:
        return {}

    # JSON form: {"uiautomator2": {"version": "2.34.1", "installed": true}, ...}
    start = out.find("{")
    if start != -1:
        try:
            data: Any = json.loads(out[start:])
        except (json.JSONDecodeError, ValueError):
            data = None
        if isinstance(data, dict):
            parsed: Dict[str, str] = {}
            for name, info in data.items():
                if isinstance(info, dict):
                    if info.get("installed") is False:
                        continue
                    ver = info.get("version") or info.get("appiumVersion") or ""
                    parsed[str(name)] = str(ver)
                else:
                    parsed[str(name)] = ""
            if parsed:
                return parsed

    # Text form: "- uiautomator2@2.34.1 [installed (npm)]".
    text_parsed: Dict[str, str] = {}
    for line in out.splitlines():
        match = _DRIVER_LINE.search(line)
        if match and "installed" in line.lower():
            text_parsed[match.group(1)] = match.group(2)
    return text_parsed


def installed_appium_drivers() -> Dict[str, str]:
    """Return installed Appium drivers as ``{name: version}``; ``{}`` on any failure.

    Shells out to ``appium driver list --installed --json`` and parses the JSON
    (falling back to the human-readable text form). Any missing binary, non-zero
    exit, timeout, or unparseable output yields an empty dict rather than raising.
    """
    try:
        proc = subprocess.run(
            ["appium", "driver", "list", "--installed", "--json"],
            capture_output=True,
            text=True,
            timeout=_DRIVER_LIST_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    # Appium prints the list to stderr; merge both streams before parsing.
    return _parse_driver_list((proc.stdout or "") + (proc.stderr or ""))


def required_driver(platform: str) -> str:
    """The Appium driver a platform needs: ``xcuitest`` for iOS, else ``uiautomator2``."""
    return "xcuitest" if platform.lower() == "ios" else "uiautomator2"


def _check_android_home(results: List[PreflightResult]) -> None:
    """Append the ANDROID_HOME check, self-healing this process's env when possible."""
    pre_set = bool(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT"))
    detected = ensure_android_home()
    if detected and pre_set:
        results.append(PreflightResult("ANDROID_HOME", True, "pass", f"Android SDK at {detected}"))
    elif detected:
        # Healed our own env, but a *separately launched* Appium server won't have it.
        results.append(
            PreflightResult(
                "ANDROID_HOME",
                True,
                "warn",
                f"ANDROID_HOME was unset; detected an Android SDK at {detected}",
                fix=f"export ANDROID_HOME={detected}",
            )
        )
    else:
        results.append(
            PreflightResult(
                "ANDROID_HOME",
                False,
                "fail",
                "No Android SDK found (ANDROID_HOME/ANDROID_SDK_ROOT unset)",
                fix="Install the Android SDK and set ANDROID_HOME to its path",
            )
        )


def preflight(platform: str, driver: str, server: str) -> List[PreflightResult]:
    """Run the environment checks that matter for a given crawl configuration.

    Fast and side-effect-free except that it calls :func:`ensure_android_home` to
    self-heal this process's env. Checks, in order:

    * ANDROID_HOME — only when it matters (Android; iOS never needs it).
    * Appium server reachability — only when a server is needed (iOS, or the
      Android ``appium`` driver).
    * The required Appium driver being installed — same server condition.

    Args:
        platform: ``"android"`` or ``"ios"``.
        driver: Android UI backend — ``"adb"`` (no server) or ``"appium"``.
        server: Appium server URL to probe.

    Returns:
        The checks that applied, as a list of :class:`PreflightResult`.
    """
    results: List[PreflightResult] = []
    plat = platform.lower()
    needs_server = plat == "ios" or driver == "appium"

    if plat == "android":
        _check_android_home(results)

    if needs_server:
        reachable, version = appium_status(server)
        if reachable:
            detail = f"Reachable at {server}" + (f" (v{version})" if version else "")
            results.append(PreflightResult("Appium server", True, "pass", detail))
        else:
            results.append(
                PreflightResult(
                    "Appium server",
                    False,
                    "fail",
                    f"No Appium server reachable at {server}",
                    fix="Start Appium (e.g. `appium`) and retry",
                )
            )

        req = required_driver(plat)
        drivers = installed_appium_drivers()
        if req in drivers:
            ver = drivers[req]
            detail = f"{req} installed" + (f" (v{ver})" if ver else "")
            results.append(PreflightResult(f"Appium driver: {req}", True, "pass", detail))
        else:
            results.append(
                PreflightResult(
                    f"Appium driver: {req}",
                    False,
                    "warn",
                    f"Required Appium driver '{req}' is not installed",
                    fix=f"appium driver install {req}",
                )
            )

    return results
