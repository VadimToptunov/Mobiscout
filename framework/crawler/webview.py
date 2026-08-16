"""
General WebView support ("Mode 2") for the Appium crawler drivers.

Hybrid apps host web content in a native WebView. Two regimes:

  * **Mode 1 — web projected into the native tree.** The accessibility tree
    already exposes the web controls as native nodes; the crawler sees them with
    no help. Nothing here is needed.
  * **Mode 2 — opaque WebView.** The native tree shows one WebView node with no
    interactive children. The web content is only reachable by switching the
    Appium *context* to the ``WEBVIEW_*`` (Chromedriver on Android, the remote
    web inspector on iOS) and walking the DOM.

This module makes Mode 2 transparent to the crawler. When a WebView context with
live DOM is present, :func:`web_snapshot` enumerates the interactive DOM elements
in one JS call and renders them as **uiautomator-style XML** — the exact format
``parse_screen`` already consumes on both platforms — so web content becomes a
first-class crawl surface (inventory, graph, generated tests) with no change to
the crawler or the parser. Taps and typing map back to the real DOM element (by
an injected ``data-mtr-id``), so the crawler's ``tap(*element.center)`` drives
the web element directly instead of guessing device coordinates.

Device-free: the XML synthesis (:func:`build_web_screen`) is pure and unit
tested; only :func:`web_snapshot` / :func:`click_web` / :func:`type_web` touch a
live Appium session.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

# After a button/link/submit click we briefly stay in the web context before
# returning to native. A submit fires the page's onsubmit handler (often a native
# JS bridge -> an async transition); switching context away immediately tears down
# the in-flight JS before the handler runs, silently dropping the submit. An input
# focus-click can't navigate, so it skips this (kept fast).
_WEB_NAV_SETTLE = 0.7

# Interactive DOM elements worth crawling: links, buttons, form fields, and
# anything explicitly given a button/link role or a click handler.
_INTERACTIVE_CSS = "a,button,input,textarea,select,[role=button],[role=link],[onclick]"

# One round-trip: tag every visible interactive element with a stable id
# (``data-mtr-id``) so a later tap can re-find it, and return its geometry/label.
# arguments[0] is the CSS selector. Runs as a function body, so ``return`` works.
_ENUM_JS = r"""
// A WebView context lingers in the view hierarchy after its screen is dismissed
// (e.g. once a web login hands off to a native screen). The lingering page still
// answers Chromedriver but is not on screen, so serving its DOM would trap the
// crawler on a stale screen. document.visibilityState is 'hidden' exactly then —
// bail so the driver falls back to the native tree.
if (document.hidden || document.visibilityState !== 'visible') return [];
var out = [];
var els = document.querySelectorAll(arguments[0]);
for (var i = 0; i < els.length; i++) {
  var el = els[i];
  var r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) continue;
  var cs = window.getComputedStyle(el);
  if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue;
  el.setAttribute('data-mtr-id', String(i));
  var t = (el.innerText || el.value || el.getAttribute('aria-label') ||
           el.getAttribute('placeholder') || el.getAttribute('name') || '').trim();
  out.push({
    i: i, tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || '').toLowerCase(),
    text: t.slice(0, 80), name: (el.getAttribute('name') || el.id || ''),
    x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)
  });
}
return out;
"""


def _class_for(tag: str, typ: str) -> str:
    """Map an HTML tag to the Android widget class whose *name* carries the right
    semantics for the parser and waypoints — inputs must contain "EditText" so
    ``waypoints._is_input`` recognises them; everything else is tappable."""
    if tag in ("input", "textarea"):
        if typ in ("submit", "button", "reset", "checkbox", "radio", "image"):
            return "android.widget.Button"
        return "android.widget.EditText"
    if tag == "select":
        return "android.widget.Spinner"
    if tag == "button":
        return "android.widget.Button"
    if tag == "a":
        return "android.widget.TextView"
    return "android.view.View"


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_web_screen(
    nodes: List[Dict[str, Any]], origin: Tuple[int, int] = (0, 0)
) -> Tuple[str, Dict[Tuple[int, int], int]]:
    """Render enumerated DOM nodes as uiautomator XML + a ``center -> data-mtr-id``
    map. The map lets a tap on ``element.center`` resolve back to the DOM element.
    ``origin`` offsets the (viewport-relative) DOM rects by the WebView's on-screen
    position; the coordinates only need to be internally consistent (tapping goes
    through the DOM, not the device point)."""
    ox, oy = origin
    parts = ['<hierarchy rotation="0">']
    centers: Dict[Tuple[int, int], int] = {}
    for n in nodes:
        x1 = ox + int(n["x"])
        y1 = oy + int(n["y"])
        x2 = x1 + int(n["w"])
        y2 = y1 + int(n["h"])
        if x2 <= x1 or y2 <= y1:
            continue
        cls = _class_for(str(n.get("tag", "")), str(n.get("type", "")))
        is_input = cls.endswith("EditText")
        # Matches CrawlElement.center exactly: (x1 + x2) // 2, (y1 + y2) // 2.
        centers[((x1 + x2) // 2, (y1 + y2) // 2)] = int(n["i"])
        parts.append(
            '<node class="%s" resource-id="%s" text="%s" content-desc="" '
            'bounds="[%d,%d][%d,%d]" clickable="true" focusable="%s" password="%s" enabled="true"/>'
            % (
                cls,
                _esc(str(n.get("name", ""))),
                _esc(str(n.get("text", ""))),
                x1,
                y1,
                x2,
                y2,
                str(is_input).lower(),
                str(str(n.get("type", "")) == "password").lower(),
            )
        )
    parts.append("</hierarchy>")
    return "\n".join(parts), centers


def web_context_name(driver: Any) -> Optional[str]:
    """The first ``WEBVIEW_*`` context, or None. Cheap: just reads the context
    list (which is what tells us whether the current screen hosts web content)."""
    try:
        ctxs = driver.contexts
    except Exception:
        return None
    for c in ctxs or []:
        if isinstance(c, str) and c.upper().startswith("WEBVIEW"):
            return c
    return None


def _to_native(driver: Any) -> None:
    try:
        driver.switch_to.context("NATIVE_APP")
    except Exception:
        pass


def _blank_current_if_hidden(driver: Any) -> bool:
    """With the driver ALREADY switched into a WebView context, blank it
    (``window.stop()`` + navigate to ``about:blank``) if it's hidden, so it stops
    churning the a11y tree and wedging the native dump. Idempotent (skips a context
    already on about:blank). Returns whether it blanked. Does not switch contexts —
    the caller owns that, which is what lets the hot path reuse a switch it already
    made instead of paying a second ``contexts`` round-trip."""
    try:
        if driver.execute_script("return document.visibilityState") == "visible":
            return False
        try:
            if "about:blank" in (driver.current_url or ""):
                return False
        except Exception:
            pass
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        driver.get("about:blank")
        return True
    except Exception:
        return False


def web_snapshot(
    driver: Any, ready_polls: int = 0, poll_wait: float = 0.4, neutralize_hidden: bool = False
) -> Optional[Dict[str, Any]]:
    """If the current screen hosts a WebView context with interactive DOM, return
    ``{"xml", "centers", "ctx", "focused"}`` and leave the driver in NATIVE_APP;
    else None. The XML is drop-in for ``parse_screen``.

    ``neutralize_hidden`` (Android): when the context is present but has no drivable
    DOM (a lingering hidden WebView), blank it right here — in the context we've
    already switched into — so the native dump doesn't wedge. Folding it in avoids a
    second ``driver.contexts`` call (each is an ``adb shell`` round-trip), which is
    what stresses adb on a long crawl.

    ``ready_polls`` retries a few times (waiting ``poll_wait`` s each) for the
    WebView to become drivable — both for the context to *attach* (Chromedriver /
    the remote inspector takes a few seconds after a WebView appears) and for its
    DOM to paint. Without it a just-launched hybrid screen's first read falls back
    to the (opaque, slow-to-dump) native tree. Callers pass this only before the
    first web screen is seen, so native screens after it pay nothing."""
    ctx = None
    nodes = None
    for attempt in range(ready_polls + 1):
        ctx = web_context_name(driver)
        if ctx:
            try:
                driver.switch_to.context(ctx)
                nodes = driver.execute_script(_ENUM_JS, _INTERACTIVE_CSS)
            except Exception:
                _to_native(driver)
                return None
            if nodes:
                break
            # No drivable DOM. On Android, a hidden lingering WebView here would
            # wedge the native dump — blank it in this same context (no extra
            # contexts call / switch).
            if neutralize_hidden:
                _blank_current_if_hidden(driver)
        if attempt < ready_polls:
            time.sleep(poll_wait)  # wait for the context to attach / the DOM to paint, then re-check
    if not ctx:
        return None
    _to_native(driver)
    if not nodes:
        return None
    xml, centers = build_web_screen(nodes)
    if not centers:
        return None
    return {"xml": xml, "centers": centers, "ctx": ctx, "focused": None}


def neutralize_hidden_webviews(driver: Any) -> int:
    """Blank any lingering *hidden* WebView by navigating its web context to
    ``about:blank`` (after ``window.stop()``). A hybrid app that hands a web login
    off to a native screen often leaves the WebView alive but hidden, still running
    JS — which keeps the a11y tree busy and makes the native uiautomator dump hang
    indefinitely (Android's hybrid-crawl "wall"). Blanking it stops that churn so
    the native dump settles. Idempotent (skips a context already on about:blank),
    returns how many it blanked, and leaves the driver in NATIVE_APP.

    Android-only by intent (iOS/WDA reads the native tree fine past a hidden
    WKWebView); the caller decides when to invoke it."""
    try:
        contexts = driver.contexts
    except Exception:
        return 0
    blanked = 0
    for ctx in contexts or []:
        if not (isinstance(ctx, str) and ctx.upper().startswith("WEBVIEW")):
            continue
        try:
            driver.switch_to.context(ctx)
            if _blank_current_if_hidden(driver):
                blanked += 1
        except Exception:
            pass
    _to_native(driver)
    return blanked


def _nearest(centers: Dict[Tuple[int, int], int], x: int, y: int, tol: int = 6) -> Optional[int]:
    """The data-mtr-id of the web node whose center is at (x, y) — exact, or the
    nearest within ``tol`` px (the crawler taps the exact center, so this almost
    always hits exactly; the tolerance only absorbs integer rounding)."""
    if (x, y) in centers:
        return centers[(x, y)]
    best: Optional[int] = None
    best_d = tol * tol + 1
    for (cx, cy), i in centers.items():
        d = (cx - x) ** 2 + (cy - y) ** 2
        if d < best_d:
            best_d = d
            best = i
    return best if best_d <= tol * tol else None


def click_web(driver: Any, web: Dict[str, Any], x: int, y: int) -> bool:
    """Tap (x, y) resolved to the DOM element and click it in the web context.
    Remembers a clicked input as ``focused`` so a following type goes to it.
    Returns to NATIVE_APP so the driver's native ops (back/tap) behave. False if
    (x, y) isn't a known web node."""
    i = _nearest(web["centers"], x, y)
    if i is None:
        return False
    from selenium.webdriver.common.by import By

    try:
        driver.switch_to.context(web["ctx"])
        el = driver.find_element(By.CSS_SELECTOR, '[data-mtr-id="%d"]' % i)
        tag = (el.tag_name or "").lower()
        el.click()
        if tag in ("input", "textarea"):
            web["focused"] = i
        else:
            web["focused"] = None
            time.sleep(_WEB_NAV_SETTLE)  # let a submit's JS handler / native transition run before we leave the web context
        return True
    except Exception:
        return False
    finally:
        _to_native(driver)


def type_web(driver: Any, web: Dict[str, Any], text: str) -> bool:
    """Type into the last-clicked web input (or the active element), sending real
    key events so controlled inputs (React/Vue) register the value. Returns to
    NATIVE_APP afterward."""
    from selenium.webdriver.common.by import By

    i = web.get("focused")
    try:
        driver.switch_to.context(web["ctx"])
        el = (
            driver.find_element(By.CSS_SELECTOR, '[data-mtr-id="%d"]' % i)
            if i is not None
            else driver.switch_to.active_element
        )
        el.send_keys(text)
        return True
    except Exception:
        return False
    finally:
        _to_native(driver)
