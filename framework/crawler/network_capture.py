"""
Capture the app's HTTP traffic DURING a crawl, so a crawl alone yields API tests (#312).

The consumer side already exists — a proxy HAR becomes ``test_api.py`` (``crawl --har``,
``emit_api_tests_from_har``). This is the producer: mitmproxy's ``mitmdump`` runs for the
length of the crawl and writes the traffic it proxies as a HAR (mitmproxy's own ``hardump``),
and the device is pointed at it:

* **Android** (emulator or device): ``adb shell settings put global http_proxy host:port`` —
  ``10.0.2.2`` (the emulator's alias for the host) or the host's LAN address for a device —
  and **always** reset (``:0``) afterwards, even when the crawl fails;
* **iOS Simulator**: it uses the Mac's network, so it is routed by the Mac's proxy settings.
  Changing those would reroute the whole machine, which a crawl must not do behind your back:
  the capture runs, and :attr:`NetworkCapture.instructions` says what to set.

HTTPS is captured only where the device trusts mitmproxy's CA (``~/.mitmproxy``): on Android
an app must opt in to user CAs (``network_security_config``), as debug builds usually do.
"""

from __future__ import annotations

import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, List, Optional

from framework.utils.logger import get_logger

logger = get_logger(__name__)

EMULATOR_HOST = "10.0.2.2"  # the Android emulator's alias for the host machine


class NetworkCaptureError(RuntimeError):
    """The capture could not start (mitmproxy missing, the proxy never came up)."""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _lan_address() -> str:
    """The host's address on the network a physical device shares with it."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("10.255.255.255", 1))  # no packet is sent; it only picks the route
            return str(sock.getsockname()[0])
        except OSError:
            return "127.0.0.1"


class NetworkCapture:
    """``with NetworkCapture(har, platform="android", serial=...)``: mitmdump runs and the device
    is routed through it for the block; on exit the route is reset and the HAR written.

    ``run`` / ``spawn`` / ``which`` are injectable (subprocess.run / Popen / shutil.which), so the
    lifecycle is unit-testable without mitmproxy or a device."""

    def __init__(
        self,
        har_path: Path,
        platform: str = "android",
        serial: Optional[str] = None,
        port: Optional[int] = None,
        run: Callable[..., Any] = subprocess.run,
        spawn: Callable[..., Any] = subprocess.Popen,
        which: Callable[[str], Optional[str]] = shutil.which,
    ):
        self.har_path = Path(har_path)
        self.platform = platform
        self.serial = serial
        self.port = port or _free_port()
        self.instructions = ""
        self._run, self._spawn, self._which = run, spawn, which
        self._process: Any = None
        self._routed = False

    # --- lifecycle -------------------------------------------------------------------------
    def __enter__(self) -> "NetworkCapture":
        mitmdump = self._which("mitmdump")
        if mitmdump is None:
            raise NetworkCaptureError(
                "Network capture needs mitmproxy: install it (`pip install mitmproxy` or "
                "`brew install mitmproxy`) and retry, or crawl without --capture-network."
            )
        self.har_path.parent.mkdir(parents=True, exist_ok=True)
        self._process = self._spawn(
            [mitmdump, "--quiet", "--listen-host", "0.0.0.0", "--listen-port", str(self.port)]
            + ["--set", f"hardump={self.har_path}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_listening()
        self._route()
        return self

    def __exit__(self, *_exc: Any) -> None:
        try:
            self._unroute()
        finally:
            self._stop()

    # --- the proxy -------------------------------------------------------------------------
    def _wait_listening(self, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise NetworkCaptureError(f"mitmdump exited at start (code {self._process.returncode})")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.2)
        self._stop()
        raise NetworkCaptureError(f"mitmdump did not start listening on port {self.port} within {timeout:.0f}s")

    def _stop(self) -> None:
        """SIGINT, so mitmdump writes the HAR on its way out; kill it if it hangs."""
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()

    # --- the device ------------------------------------------------------------------------
    def _adb(self, *args: str) -> List[str]:
        return ["adb", *(["-s", self.serial] if self.serial else []), *args]

    def _route(self) -> None:
        if self.platform != "android":
            self.instructions = (
                f"iOS Simulator traffic is not routed automatically (it uses the Mac's network): set the "
                f"Mac's HTTP/HTTPS proxy to 127.0.0.1:{self.port} for the crawl and trust mitmproxy's CA "
                "in the simulator, then turn the proxy off again."
            )
            logger.warning(self.instructions)
            return
        is_emulator = (self.serial or "").startswith("emulator-") or self.serial is None
        host = EMULATOR_HOST if is_emulator else _lan_address()
        self._run(self._adb("shell", "settings", "put", "global", "http_proxy", f"{host}:{self.port}"), check=False)
        self._routed = True

    def _unroute(self) -> None:
        if self._routed:
            self._run(self._adb("shell", "settings", "put", "global", "http_proxy", ":0"), check=False)
            self._routed = False

    # --- the result ------------------------------------------------------------------------
    @property
    def captured(self) -> Optional[str]:
        """The HAR path, once it holds at least one entry; else None."""
        if not self.har_path.exists():
            return None
        import json

        try:
            entries = json.loads(self.har_path.read_text(encoding="utf-8")).get("log", {}).get("entries", [])
        except (ValueError, OSError):
            return None
        return str(self.har_path) if entries else None
