"""Device management for CLI daemon."""

import json
import os
import re
import subprocess
import tempfile
from typing import List, Dict, Any, Optional, Tuple

# adb's first call after boot also starts the adb server ("* daemon not running"),
# which on a cold machine (or behind a Windows firewall prompt) outlasts a tight
# budget — a timeout there is indistinguishable from "no devices attached".
_ADB_LIST_TIMEOUT = 10

# The trailing "<major>-<minor>[-<patch>]" of a simctl runtime identifier, e.g.
# "com.apple.CoreSimulator.SimRuntime.iOS-26-3".
_RUNTIME_VERSION = re.compile(r"(\d+)-(\d+)(?:-(\d+))?$")

# AVD names are restricted to this charset. Emulator 34.x/35.x print an INFO
# diagnostic on stdout before the list, which would otherwise show up as a
# bootable "AVD" in the plugin's dropdown.
_AVD_NAME = re.compile(r"[A-Za-z0-9_.-]+")

# How long to watch a freshly launched emulator before reporting "starting": a
# bad or locked AVD (and a missing KVM/HAXM) kills it in well under a second.
_EMULATOR_START_GRACE = 1.5


class DeviceManager:
    """Manage Android and iOS devices/simulators."""

    @staticmethod
    def probe_android_devices() -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """List Android devices via adb, plus the reason the probe failed.

        An empty list on its own cannot be told apart from "adb is missing" or "adb
        timed out", which is how a broken toolchain gets reported to the user as
        "no devices". Returns ``(devices, error)``; ``error`` is ``None`` on a
        clean listing.
        """
        devices = []
        try:
            # text=True alone decodes with the locale codepage (cp1252/cp936 on
            # Windows), where a non-ASCII OEM model name raises UnicodeDecodeError
            # or mojibakes; pin UTF-8 with replacement on every text call here.
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_ADB_LIST_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return [], f"adb devices timed out after {_ADB_LIST_TIMEOUT}s"
        except FileNotFoundError:
            return [], "adb not found on PATH (install the Android SDK platform-tools)"

        if result.returncode != 0:
            return [], (result.stderr or "").strip() or f"adb devices exited with code {result.returncode}"

        lines = result.stdout.strip().split("\n")[1:]  # Skip header
        for line in lines:
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]

                    # Get device info
                    name = DeviceManager._get_android_device_name(device_id)
                    api_level = DeviceManager._get_android_api_level(device_id)

                    devices.append(
                        {
                            "id": device_id,
                            "name": name,
                            "platform": "android",
                            "status": "online" if status == "device" else status,
                            "api_level": api_level,
                        }
                    )

        return devices, None

    @staticmethod
    def list_android_devices() -> List[Dict[str, Any]]:
        """List Android devices via adb (``[]`` when the probe fails —
        :meth:`probe_android_devices` keeps the reason)."""
        return DeviceManager.probe_android_devices()[0]

    @staticmethod
    def probe_ios_simulators() -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """List iOS simulators via simctl, plus the reason the probe failed.

        Same contract as :meth:`probe_android_devices`: ``(devices, error)``, so a
        missing/hung/unparseable simctl is not reported as "no simulators".
        """
        devices = []
        try:
            result = subprocess.run(
                ["xcrun", "simctl", "list", "devices", "-j"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            return [], "xcrun simctl list timed out after 5s"
        except FileNotFoundError:
            return [], "xcrun not found on PATH (install Xcode command-line tools)"

        if result.returncode != 0:
            return [], (result.stderr or "").strip() or f"xcrun simctl list exited with code {result.returncode}"

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return [], "could not parse `xcrun simctl list` output"

        for runtime, device_list in data.get("devices", {}).items():
            for device in device_list:
                if device.get("isAvailable", False):
                    devices.append(
                        {
                            "id": device["udid"],
                            "name": device["name"],
                            "platform": "ios",
                            "status": device["state"].lower(),
                            "ios_version": DeviceManager._ios_version(runtime),
                        }
                    )

        return devices, None

    @staticmethod
    def list_ios_simulators() -> List[Dict[str, Any]]:
        """List iOS simulators via simctl (``[]`` when the probe fails —
        :meth:`probe_ios_simulators` keeps the reason)."""
        return DeviceManager.probe_ios_simulators()[0]

    @staticmethod
    def _ios_version(runtime: str) -> str:
        """Plain version ("26.3") from a simctl runtime key.

        The JSON keys are identifiers ("com.apple.CoreSimulator.SimRuntime.iOS-26-3"),
        so the trailing token is "iOS-26-3" — not a version, and pool ``min_version``
        filters silently fall back to lexicographic ordering on it. Falls back to the
        raw trailing token when the key has no version-shaped tail.
        """
        match = _RUNTIME_VERSION.search(runtime)
        if match:
            return ".".join(part for part in match.groups() if part)
        return runtime.split(".")[-1]

    @staticmethod
    def probe_all_devices(platform: str = "all") -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """List devices *and* report why a listing failed, if it did.

        Same filter as :meth:`list_all_devices`, but returns ``(devices, error)`` so a
        caller can tell "the tooling is broken" (adb missing, adb timed out, simctl
        returned junk) from "no devices are attached" — an empty list means the same thing
        in both cases, which is why the IDE used to show a bare empty device panel with adb
        perfectly installed. Errors from both platforms are joined, since an "all" listing
        can half-fail (adb missing on a Mac that still has simulators).
        """
        devices: List[Dict[str, Any]] = []
        errors: List[str] = []

        if platform in ("all", "android"):
            found, error = DeviceManager.probe_android_devices()
            devices.extend(found)
            if error:
                errors.append(error)

        if platform in ("all", "ios"):
            found, error = DeviceManager.probe_ios_simulators()
            devices.extend(found)
            if error:
                errors.append(error)

        return devices, "; ".join(errors) or None

    @staticmethod
    def list_all_devices(platform: str = "all") -> List[Dict[str, Any]]:
        """List all devices based on platform filter (errors dropped —
        :meth:`probe_all_devices` when the caller can report them)."""
        return DeviceManager.probe_all_devices(platform)[0]

    @staticmethod
    def _get_android_device_name(device_id: str) -> str:
        """Get Android device model name."""
        try:
            result = subprocess.run(
                ["adb", "-s", device_id, "shell", "getprop", "ro.product.model"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=2,
            )
            return result.stdout.strip() or device_id
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
            return device_id

    @staticmethod
    def _get_android_api_level(device_id: str) -> Optional[int]:
        """Get Android API level."""
        try:
            result = subprocess.run(
                ["adb", "-s", device_id, "shell", "getprop", "ro.build.version.sdk"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=2,
            )
            return int(result.stdout.strip())
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, ValueError, OSError):
            return None

    @staticmethod
    def list_ios_devices() -> List[Dict[str, Any]]:
        """List iOS devices (alias for list_ios_simulators)."""
        return DeviceManager.list_ios_simulators()

    @staticmethod
    def get_device(device_id: str) -> Optional[Dict[str, Any]]:
        """Get device by ID."""
        all_devices = DeviceManager.list_all_devices()
        for device in all_devices:
            if device.get("id") == device_id:
                return device
        return None

    @staticmethod
    def check_device_health(device_id: str) -> Dict[str, Any]:
        """Check device health status."""
        device = DeviceManager.get_device(device_id)
        if not device:
            return {"healthy": False, "error": "Device not found"}

        return {
            "healthy": device.get("status") in ("online", "booted"),
            "status": device.get("status"),
            "device_id": device_id,
            "platform": device.get("platform"),
        }

    @staticmethod
    def get_available_devices() -> List[Dict[str, Any]]:
        """Get all available (online) devices."""
        all_devices = DeviceManager.list_all_devices()
        return [d for d in all_devices if d.get("status") in ("online", "booted")]

    @staticmethod
    def get_all_devices() -> List[Dict[str, Any]]:
        """Get all devices (alias for list_all_devices)."""
        return DeviceManager.list_all_devices()

    @staticmethod
    def list_avds() -> List[str]:
        """List installed Android AVDs (bootable emulator images) via ``emulator``.

        Only AVD-name-shaped lines are kept: emulator 34.x/35.x print diagnostics
        ("INFO | Storing crashdata in: ...") on stdout, and an unfiltered line ends
        up in the plugin's dropdown as a bootable target.
        """
        try:
            result = subprocess.run(
                ["emulator", "-list-avds"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if result.returncode == 0:
                lines = (line.strip() for line in result.stdout.splitlines())
                return [line for line in lines if _AVD_NAME.fullmatch(line)]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return []

    @staticmethod
    def start_device(platform: str, target: str) -> Dict[str, Any]:
        """Boot an emulator/simulator.

        Args:
            platform: "android" or "ios".
            target: the Android AVD name, or the iOS simulator UDID.

        Returns:
            A status dict. Android boots asynchronously (the emulator process is
            launched detached and takes a while to come online), so it reports
            ``"starting"``; iOS reports the ``simctl boot`` outcome. On a missing
            tool or failure, ``{"started": False, "error": ...}``.
        """
        if not target:
            return {"started": False, "error": "target (AVD name / simulator UDID) is required"}
        try:
            if platform == "android":
                # Detached: the emulator runs for the length of the session, well
                # beyond this RPC call, so we don't wait on it. But an unknown or
                # locked AVD (and a missing KVM/HAXM) makes it exit immediately, so
                # watch it for a moment first — reporting "starting" for a process
                # that is already dead leaves the caller waiting for a device that
                # never appears, with the emulator's own diagnosis discarded.
                # Both streams go to a temp file rather than a pipe: nothing reads
                # the pipe once we return, so a long-running emulator would
                # eventually block writing to it. The file is unlinked on creation,
                # so it disappears with the process.
                with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as log:
                    proc = subprocess.Popen(
                        ["emulator", "-avd", target],
                        stdout=log,
                        stderr=log,
                    )
                    try:
                        proc.wait(timeout=_EMULATOR_START_GRACE)
                    except subprocess.TimeoutExpired:
                        return {"started": True, "platform": "android", "target": target, "status": "starting"}
                    log.seek(0)
                    lines = [line.strip() for line in log.read().splitlines() if line.strip()]
                # The emulator logs the reason ("ERROR | Unknown AVD name [...]",
                # "PANIC: ...") on stdout on current versions and on stderr on older
                # ones — hence both streams; keep the failing lines over the banner.
                fatal = [line for line in lines if "ERROR" in line or "PANIC" in line]
                return {
                    "started": False,
                    "error": " ".join((fatal or lines)[-3:]) or f"emulator exited with code {proc.returncode}",
                }
            if platform == "ios":
                result = subprocess.run(
                    ["xcrun", "simctl", "boot", target],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                # simctl exits non-zero if the device is already booted — treat that
                # as success rather than an error.
                already = "current state: Booted" in (result.stderr or "")
                if result.returncode == 0 or already:
                    return {"started": True, "platform": "ios", "target": target, "status": "booted"}
                return {"started": False, "error": result.stderr.strip() or "simctl boot failed"}
            return {"started": False, "error": f"unsupported platform: {platform}"}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            return {"started": False, "error": str(e)}

    @staticmethod
    def stop_device(platform: str, device_id: str) -> Dict[str, Any]:
        """Shut down a running emulator/simulator.

        Android uses ``adb -s <id> emu kill``; iOS uses ``xcrun simctl shutdown``.
        Returns ``{"stopped": bool, ...}``.
        """
        if not device_id:
            return {"stopped": False, "error": "device_id is required"}
        try:
            if platform == "android":
                cmd = ["adb", "-s", device_id, "emu", "kill"]
            elif platform == "ios":
                cmd = ["xcrun", "simctl", "shutdown", device_id]
            else:
                return {"stopped": False, "error": f"unsupported platform: {platform}"}
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
            # simctl exits non-zero when the simulator is already off; the desired
            # state holds, so that is not an error (mirrors the boot path above).
            already = platform == "ios" and "current state: Shutdown" in (result.stderr or "")
            if result.returncode == 0 or already:
                return {"stopped": True, "platform": platform, "device_id": device_id}
            return {"stopped": False, "error": result.stderr.strip() or "shutdown failed"}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            return {"stopped": False, "error": str(e)}

    @staticmethod
    def install_app(platform: str, device_id: str, app_path: str) -> Dict[str, Any]:
        """Install a build (.apk / .app) onto a device/simulator.

        Android uses ``adb -s <device_id> install -r <app_path>``; iOS uses
        ``xcrun simctl install <device_id|booted> <app_path>``. The path is
        validated first. adb exits 0 even on some install failures (printing
        ``Failure ...`` to stdout), so that is treated as a failure too.

        Never raises — returns ``{"ok": False, "detail": ...}`` on any error.
        Returns ``{"ok": bool, "detail": str, "platform": str, "device_id": str}``.
        """
        if not app_path:
            return {"ok": False, "detail": "app_path is required"}
        if not os.path.exists(app_path):
            return {"ok": False, "detail": f"app path does not exist: {app_path}"}
        try:
            if platform == "android":
                cmd = ["adb", "-s", device_id, "install", "-r", app_path]
            elif platform == "ios":
                cmd = ["xcrun", "simctl", "install", device_id or "booted", app_path]
            else:
                return {"ok": False, "detail": f"unsupported platform: {platform}"}
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180
            )
            # adb prints "Failure ..." to stdout while still exiting 0, so check both.
            if result.returncode == 0 and "Failure" not in (result.stdout or ""):
                return {"ok": True, "detail": "installed", "platform": platform, "device_id": device_id}
            detail = (result.stderr or "").strip() or (result.stdout or "").strip() or f"exit code {result.returncode}"
            return {"ok": False, "detail": detail, "platform": platform, "device_id": device_id}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            return {"ok": False, "detail": str(e)}

    @staticmethod
    def uninstall_app(platform: str, device_id: str, package: str) -> Dict[str, Any]:
        """Remove an installed app from a device/simulator.

        Android uses ``adb -s <device_id> uninstall <package>``; iOS uses
        ``xcrun simctl uninstall <device_id|booted> <package>``. As with
        :meth:`install_app`, adb's exit-0 ``Failure ...`` stdout counts as a
        failure.

        Never raises — returns ``{"ok": False, "detail": ...}`` on any error.
        Returns ``{"ok": bool, "detail": str, "platform": str, "device_id": str}``.
        """
        if not package:
            return {"ok": False, "detail": "package is required"}
        try:
            if platform == "android":
                cmd = ["adb", "-s", device_id, "uninstall", package]
            elif platform == "ios":
                cmd = ["xcrun", "simctl", "uninstall", device_id or "booted", package]
            else:
                return {"ok": False, "detail": f"unsupported platform: {platform}"}
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            # adb prints "Failure ..." to stdout while still exiting 0, so check both.
            if result.returncode == 0 and "Failure" not in (result.stdout or ""):
                return {"ok": True, "detail": "uninstalled", "platform": platform, "device_id": device_id}
            detail = (result.stderr or "").strip() or (result.stdout or "").strip() or f"exit code {result.returncode}"
            return {"ok": False, "detail": detail, "platform": platform, "device_id": device_id}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            return {"ok": False, "detail": str(e)}
