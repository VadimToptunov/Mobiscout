"""
Make the Android SDK tools discoverable, even under a GUI app's minimal PATH.

macOS hands a GUI process (an IDE launched from Finder/Dock) a bare launchd PATH —
``/usr/bin:/bin:/usr/sbin:/sbin`` — so ``xcrun``/``simctl`` (in ``/usr/bin``) work but
``adb``/``emulator`` (under ``~/Library/Android/sdk`` or Homebrew's ``/opt/homebrew/bin``)
are invisible. The engine, launched by the plugin, inherits that PATH — so Android
devices/AVDs silently don't appear and crawls can't reach the device, while iOS is fine.

[[ensure_tooling_on_path]] resolves the SDK (env vars, then the per-OS default location)
and prepends its tool dirs — plus the common Homebrew/local bins where ``adb``/``node``/
``appium`` also live — to ``PATH`` once at startup. Every bare ``adb``/``emulator`` call
in the engine then resolves, with no per-call-site change. Idempotent and cross-platform;
adds only directories that exist, so it's a no-op where nothing is found.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

# Homebrew / common bin dirs where adb, node and appium are often installed. A GUI
# PATH omits these too. os.path.isdir filters out the ones absent on a given OS.
_COMMON_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin")


def sdk_root() -> Optional[Path]:
    """The Android SDK root: ``ANDROID_HOME`` / ``ANDROID_SDK_ROOT`` if set to a real
    directory, else the per-OS default install location. ``None`` if none exists."""
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(env)
        if value and Path(value).is_dir():
            return Path(value)
    home = Path.home()
    for candidate in (
        home / "Library" / "Android" / "sdk",  # macOS
        home / "Android" / "Sdk",  # Linux
        home / "AppData" / "Local" / "Android" / "Sdk",  # Windows
    ):
        if candidate.is_dir():
            return candidate
    return None


def _sdk_tool_dirs(root: Path) -> List[Path]:
    """The SDK sub-dirs that hold the CLI tools we shell out to."""
    dirs = [
        root / "platform-tools",  # adb
        root / "emulator",  # emulator
        root / "cmdline-tools" / "latest" / "bin",  # avdmanager, sdkmanager
        root / "tools" / "bin",  # legacy avdmanager
    ]
    return [d for d in dirs if d.is_dir()]


def ensure_tooling_on_path() -> None:
    """Idempotently prepend the Android SDK tool dirs + common bin dirs to ``PATH`` and
    export ``ANDROID_HOME`` when it's unset but an SDK was found. Safe to call repeatedly;
    a no-op when nothing resolves."""
    root = sdk_root()
    extra: List[str] = [str(d) for d in (_sdk_tool_dirs(root) if root else [])]
    extra += [d for d in _COMMON_BIN_DIRS if os.path.isdir(d)]
    if not extra:
        return

    parts = os.environ.get("PATH", "").split(os.pathsep)
    missing = [d for d in extra if d not in parts]
    if missing:
        os.environ["PATH"] = os.pathsep.join(missing + parts)

    if root and not os.environ.get("ANDROID_HOME"):
        os.environ["ANDROID_HOME"] = str(root)
