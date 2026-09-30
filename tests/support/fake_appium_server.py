"""A device-free Appium server: the W3C WebDriver + Appium endpoints the generated kits use,
backed by a fake app model — so the JVM and .NET kits (whose clients talk to Appium over HTTP)
are EXECUTED, not just compiled, exactly like the Python and JS kits run against their fakes.

The app model is the one tests/support/kit_fake_conftest.py reads::

    {"start": int,
     "screens": [[[by, value], ...], ...],          # what each screen shows (every locator tier)
     "transitions": [[from, by, value, to], ...],   # where a tap goes
     "crashes": [[screen, by, value], ...],         # tapping it kills the APP
     "session_killers": [[screen, by, value], ...], # tapping it kills the SESSION
     "back_works": bool}

``by`` is the W3C/Appium ``using`` string ("id", "accessibility id", "xpath", "class name",
"-android uiautomator", ...), so a kit in any language resolves the same locators.

An endpoint the fake does not know answers 404 ``unknown command`` and is recorded in
``server.unknown`` — a kit calling something new fails loudly instead of passing by accident.

usage::

    with FakeAppiumServer(model) as server:
        run_kit(env={"MOBISCOUT_APPIUM_SERVER": server.url})
"""

from __future__ import annotations

import itertools
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Set, Tuple

ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"
_RUNNING_IN_FOREGROUND, _NOT_RUNNING = 4, 1


class _WebDriverError(Exception):
    """A W3C error response (status, error code, message)."""

    def __init__(self, status: int, error: str, message: str):
        super().__init__(message)
        self.status, self.error, self.message = status, error, message


class _App:
    """The fake app a session drives."""

    def __init__(self, model: Dict[str, Any]):
        self.screens = [{tuple(loc) for loc in scr} for scr in model.get("screens", [])]
        self.transitions = {(t[0], t[1], t[2]): t[3] for t in model.get("transitions", [])}
        self.crashes = {tuple(c) for c in model.get("crashes", [])}
        self.killers = {tuple(k) for k in model.get("session_killers", [])}
        self.back_works = model.get("back_works", True)
        self.start = model.get("start", 0)
        self.current: int = self.start
        self.running = True
        self.history: List[int] = []
        self.typed: Dict[Tuple[str, str], str] = {}

    def present(self, by: str, value: str) -> bool:
        return self.running and (by, value) in self.screens[self.current]

    def valid_input(self) -> bool:
        """A validating form: a submit only advances when what was typed is plausible."""
        for (_by, value), text in self.typed.items():
            v = value.lower()
            if ("email" in v or "mail" in v) and "@" not in text:
                return False
            if "password" in v and len(text) < 4:
                return False
        return True

    def tap(self, by: str, value: str) -> bool:
        """Apply a tap; returns False when it killed the session."""
        key = (self.current, by, value)
        if key in self.killers:
            return False
        if key in self.crashes:
            self.running = False
            return True
        nxt = self.transitions.get(key)
        if nxt is not None and self.valid_input():
            self.history.append(self.current)
            self.current = nxt
            self.typed.clear()
        return True

    def back(self) -> None:
        if self.back_works and self.history:
            self.current = self.history.pop()
            self.typed.clear()

    def launch(self) -> None:
        self.current, self.running, self.history = self.start, True, []
        self.typed.clear()


class FakeAppiumServer:
    """A threaded fake Appium server on a free local port. Each new session gets a fresh app."""

    def __init__(self, model: Dict[str, Any]):
        self.model = model
        self.sessions: Dict[str, _App] = {}
        self.dead: Set[str] = set()
        self.unknown: List[str] = []
        self.elements: Dict[str, Tuple[str, str]] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def __enter__(self) -> "FakeAppiumServer":
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    # --- routing -------------------------------------------------------------------------
    def handle(self, method: str, path: str, body: Dict[str, Any]) -> Any:
        """The ``value`` of the response to one request (raises _WebDriverError)."""
        path = path.rstrip("/")
        if path in ("/status", "/wd/hub/status"):
            return {"ready": True, "message": "fake appium"}
        path = re.sub(r"^/wd/hub", "", path)
        if method == "POST" and path == "/session":
            return self._new_session()
        m = re.match(r"^/session/([^/]+)(/.*)?$", path)
        if not m:
            return self._unknown(method, path)
        sid, rest = m.group(1), m.group(2) or ""
        if method == "DELETE" and rest == "":
            self.sessions.pop(sid, None)
            return None
        app = self._session(sid)
        return self._command(sid, app, method, rest, body)

    def _new_session(self) -> Dict[str, Any]:
        with self._lock:
            sid = f"session-{next(self._ids)}"
            self.sessions[sid] = _App(self.model)
        return {"sessionId": sid, "capabilities": {"platformName": "Android", "automationName": "Fake"}}

    def _session(self, sid: str) -> _App:
        if sid in self.dead or sid not in self.sessions:
            raise _WebDriverError(404, "invalid session id", f"session {sid} is gone")
        return self.sessions[sid]

    def _command(self, sid: str, app: _App, method: str, rest: str, body: Dict[str, Any]) -> Any:
        if rest in ("/element", "/elements") and method == "POST":
            return self._find(app, body.get("using", ""), body.get("value", ""), many=rest == "/elements")
        m = re.match(r"^/element/([^/]+)/(click|clear|value|displayed|enabled|text|rect|attribute/.+)$", rest)
        if m:
            return self._element(sid, app, m.group(1), m.group(2), body)
        if rest in ("/appium/device/app_state",):
            return _RUNNING_IN_FOREGROUND if app.running else _NOT_RUNNING
        if rest in ("/appium/device/terminate_app",):
            app.running = False
            return True
        if rest in ("/appium/device/activate_app",):
            app.launch()
            return None
        if rest == "/appium/settings":
            return {}
        if rest == "/back":
            app.back()
            return None
        if rest == "/window/rect":
            return {"x": 0, "y": 0, "width": 1080, "height": 1920}
        if rest in ("/execute/sync", "/execute"):
            return self._execute(app, body.get("script", ""))
        if rest in ("/timeouts", "/appium/device/hide_keyboard"):
            return None
        if rest == "/appium/device/is_keyboard_shown":
            return False
        return self._unknown(method, f"/session/:id{rest}")

    def _find(self, app: _App, by: str, value: str, many: bool) -> Any:
        found = app.present(by, value)
        if many:
            return [self._ref(by, value)] if found else []
        if not found:
            raise _WebDriverError(404, "no such element", f"{by}={value} not on screen {app.current}")
        return self._ref(by, value)

    def _ref(self, by: str, value: str) -> Dict[str, str]:
        with self._lock:
            eid = f"el-{next(self._ids)}"
            self.elements[eid] = (by, value)
        return {ELEMENT_KEY: eid}

    def _element(self, sid: str, app: _App, eid: str, action: str, body: Dict[str, Any]) -> Any:
        by, value = self.elements[eid]
        if not app.present(by, value):
            raise _WebDriverError(404, "stale element reference", f"{by}={value} is no longer on screen")
        if action == "click":
            if not app.tap(by, value):
                self.dead.add(sid)
            return None
        if action == "clear":
            app.typed[(by, value)] = ""
            return None
        if action == "value":
            app.typed[(by, value)] = body.get("text", "".join(body.get("value", [])))
            return None
        if action in ("displayed", "enabled"):
            return True
        if action == "rect":
            return {"x": 0, "y": 0, "width": 300, "height": 60}
        return ""  # text / attribute

    def _execute(self, app: _App, script: str) -> Any:
        script = re.sub(r"^mobile:\s*", "mobile: ", script.strip())  # Appium accepts both spellings
        if script in ("mobile: scroll", "mobile: scrollGesture"):
            return False  # nothing further below the fold
        if script == "mobile: isKeyboardShown":
            return False
        if script == "mobile: hideKeyboard":
            return None
        if script == "mobile: queryAppState":
            return _RUNNING_IN_FOREGROUND if app.running else _NOT_RUNNING
        if script == "mobile: terminateApp":
            app.running = False
            return True
        if script == "mobile: activateApp":
            app.launch()
            return None
        return self._unknown("EXECUTE", script)

    def _unknown(self, method: str, what: str) -> Any:
        self.unknown.append(f"{method} {what}")
        raise _WebDriverError(404, "unknown command", f"the fake Appium server does not implement {method} {what}")

    # --- HTTP ------------------------------------------------------------------------------
    def _handler(self) -> type:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _respond(self, status: int, payload: Any) -> None:
                data = json.dumps({"value": payload}).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _dispatch(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body: Dict[str, Any] = json.loads(raw) if raw.strip() else {}
                try:
                    self._respond(200, server.handle(method, self.path, body))
                except _WebDriverError as exc:
                    self._respond(exc.status, {"error": exc.error, "message": exc.message, "stacktrace": ""})

            def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
                self._dispatch("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._dispatch("POST")

            def do_DELETE(self) -> None:  # noqa: N802
                self._dispatch("DELETE")

            def log_message(self, *_args: Any) -> None:
                pass  # quiet

        return Handler


def app_state(server: FakeAppiumServer) -> Optional[int]:
    """The app state of the one live session (for tests of the fake itself)."""
    live = [a for s, a in server.sessions.items() if s not in server.dead]
    return (_RUNNING_IN_FOREGROUND if live[0].running else _NOT_RUNNING) if live else None
