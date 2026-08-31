"""Auto-start a local Appium server on a free port when one is needed but not running.

An Appium-driven crawl needs an Appium server. Making the user install Node, install
Appium, and remember to start it — before every session — is exactly the kind of setup
Mobiscout tries to remove. So when the crawl asks for the Appium driver and nothing is
reachable at the default local address, we start our *own* server on a free port, use it,
and shut it down when the crawl finishes. If Appium isn't installed at all we can't start
it, so we fall back to the actionable "install it / point at a hub" error.

We only auto-start for the default *local* server. If the caller pointed `server` at a
specific remote/cloud hub, an unreachable one is a real error worth surfacing, not
something to paper over with a local process.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from typing import Any, Callable, Dict, Optional, Tuple

from framework.crawler.errors import CrawlerDriverError
from framework.health.preflight import appium_status
from framework.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_SERVER = "http://localhost:4723"
# The default local server under any spelling the plugin/CLI might send.
_DEFAULT_LOCAL = {"", _DEFAULT_SERVER, "http://127.0.0.1:4723"}
# How long to wait for a freshly-launched server to answer /status before giving up.
_READY_TIMEOUT_S = 40.0
_READY_POLL_S = 0.5


def _is_default_local(server: Optional[str]) -> bool:
    """Whether ``server`` is the default local address (so auto-start is appropriate)
    rather than an explicit remote/cloud hub the caller chose."""
    normalized = (server or "").strip().rstrip("/")
    return normalized in {s.rstrip("/") for s in _DEFAULT_LOCAL}


def find_appium_executable() -> Optional[str]:
    """Locate the ``appium`` launcher, or None if it isn't installed.

    A GUI-launched IDE hands the engine a minimal PATH (the same reason adb needs
    resolving), so PATH alone misses a Homebrew/npm-global install. Check PATH first,
    then the common install locations."""
    exe = shutil.which("appium") or (shutil.which("appium.cmd") if os.name == "nt" else None)
    if exe:
        return exe
    home = os.path.expanduser("~")
    candidates = [
        "/opt/homebrew/bin/appium",  # Apple-silicon Homebrew
        "/usr/local/bin/appium",  # Intel Homebrew / common npm prefix
        os.path.join(home, ".npm-global/bin/appium"),
        os.path.join(home, ".volta/bin/appium"),
        os.path.join(home, "n/bin/appium"),
    ]
    if os.name == "nt":
        candidates += [
            os.path.join(os.environ.get("APPDATA", ""), "npm", "appium.cmd"),
        ]
    return next((c for c in candidates if c and os.path.isfile(c) and os.access(c, os.X_OK)), None)


def _free_port() -> int:
    """A currently-free TCP port on localhost. Small race between close and reuse, but
    Appium binds it within a second and a collision just fails the readiness wait."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ManagedAppiumServer:
    """An Appium server we launched and are responsible for stopping."""

    def __init__(self, executable: str, host: str = "127.0.0.1") -> None:
        self._executable = executable
        self._host = host
        self._proc: Optional[subprocess.Popen] = None
        self.url: str = ""

    def start(self, ready_timeout: float = _READY_TIMEOUT_S) -> "ManagedAppiumServer":
        """Launch on a free port and block until it answers /status. Raises
        CrawlerDriverError (after cleaning up the process) if it never becomes ready."""
        port = _free_port()
        self.url = f"http://{self._host}:{port}"
        # --relaxed-security so session-scoped commands the kits use (mobile: clearApp,
        # startActivity) are permitted; a new session group so we can kill node's children.
        cmd = [self._executable, "--address", self._host, "--port", str(port), "--relaxed-security"]
        popen_kwargs: Dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            popen_kwargs["start_new_session"] = True
        logger.info("Auto-starting Appium on %s", self.url)
        try:
            self._proc = subprocess.Popen(cmd, **popen_kwargs)  # noqa: S603 - fixed argv, no shell
        except Exception as exc:  # a broken install / not actually executable
            raise CrawlerDriverError(f"Could not launch Appium ({self._executable}): {exc}") from exc

        deadline = time.monotonic() + ready_timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:  # it exited on its own — port taken / bad install
                self.stop()
                raise CrawlerDriverError(f"Appium exited before it became ready (started from {self._executable}).")
            reachable, _ = appium_status(self.url)
            if reachable:
                logger.info("Auto-started Appium is ready at %s", self.url)
                return self
            time.sleep(_READY_POLL_S)
        self.stop()
        raise CrawlerDriverError(f"Auto-started Appium did not become ready within {int(ready_timeout)}s.")

    def stop(self) -> None:
        """Terminate the server (and its process group), best-effort and idempotent."""
        proc = self._proc
        self._proc = None
        if proc is None or proc.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(proc.pid), 15)  # SIGTERM the whole group
            else:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    os.killpg(os.getpgid(proc.pid), 9)  # SIGKILL
                else:
                    proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass


def _unreachable_error(target: str, appium_installed: bool) -> CrawlerDriverError:
    if not appium_installed:
        return CrawlerDriverError(
            f"Appium server not reachable at {target}, and no `appium` was found to auto-start.\n"
            "Install it (then Mobiscout will start it for you next time):\n"
            "  npm install -g appium\n"
            "  appium driver install uiautomator2   # xcuitest for iOS\n"
            "…or point 'server' at your Appium / cloud-grid hub."
        )
    return CrawlerDriverError(
        f"Appium server not reachable at {target}. Start it, or point 'server' at your " "Appium / cloud-grid hub."
    )


def ensure_appium(
    server: Optional[str],
    *,
    status: Callable[[str], Tuple[bool, Optional[str]]] = appium_status,
    finder: Callable[[], Optional[str]] = find_appium_executable,
    server_factory: Callable[[str], "ManagedAppiumServer"] = ManagedAppiumServer,
) -> Tuple[str, Optional["ManagedAppiumServer"]]:
    """Return ``(server_url, managed_or_None)`` for an Appium-driven crawl.

    If a server is already reachable, use it (no managed process). If none is reachable
    and the target is the default *local* address, auto-start one on a free port and
    return it for the caller to stop after the crawl. If Appium isn't installed, or the
    caller pointed at a specific remote hub that's down, raise an actionable error.

    The ``status``/``finder``/``server_factory`` seams keep this unit-testable without a
    real Appium install.
    """
    target = (server or "").strip() or _DEFAULT_SERVER
    reachable, _ = status(target)
    if reachable:
        return target, None
    if not _is_default_local(server):
        raise _unreachable_error(target, appium_installed=finder() is not None)
    executable = finder()
    if executable is None:
        raise _unreachable_error(target, appium_installed=False)
    managed = server_factory(executable).start()
    return managed.url, managed
