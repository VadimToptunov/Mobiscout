"""Flutter widget-tree support ("Route B") for the Appium crawler drivers.

A Flutter app paints its entire UI into one opaque ``FlutterView`` canvas, so the
native accessibility tree the crawler normally reads shows a single node with no
interactive children. Two regimes, mirroring the WebView split in
:mod:`framework.crawler.webview`:

  * **Route A — semantics projected into the native tree.** When the app has
    accessibility enabled, Flutter's ``SemanticsNode`` tree surfaces into the
    native a11y tree (content-desc / labels) and the crawler sees *some* controls
    with no help. Coverage depends on the app labelling its widgets, so it is a
    partial, best-effort path. ``parse_screen`` already tags such a screen
    ``toolkit="flutter"`` off the ``FlutterView`` class name.
  * **Route B — the Flutter integration server.** The real widget tree is only
    reachable through the ``appium-flutter-integration-driver``
    (``automationName=FlutterIntegration``), which runs an HTTP server on the Dart
    VM *inside the app under test* and exposes real finders (``ValueKey``, widget
    type, text, semantics label).

    **Build requirement (confirmed against the driver's README, v2.0.3):** the app
    must cooperate — a ``appium_flutter_server`` dev dependency plus an
    ``integration_test/appium_test.dart`` entry point calling ``initializeTest``,
    built with that target. It **cannot** attach to an arbitrary third-party
    release APK/IPA with no source changes. Route B is therefore for a team testing
    **their own** Flutter app (they own the build), which is exactly Mobiscout's
    source-aware user; crawling a foreign installed app stays on Route A / positional.

This module makes Route B transparent to the crawler the same way ``webview`` does
for Mode 2: :func:`build_flutter_screen` renders enumerated Flutter widgets as
**uiautomator-style XML** — the exact format ``parse_screen`` already consumes — so
the widget tree becomes a first-class crawl surface with no change to the crawler or
parser. A widget's ``ValueKey`` lands in the locator field (``resource-id``), its
semantics label in ``content-desc``, so codegen emits a stable Flutter finder
instead of a positional tap.

Device-free: the XML synthesis here is pure and unit tested. The live enumeration /
tap / type layer that drives a real integration-server session is a later increment
(it needs a driver-enabled Flutter build to validate against a device).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Flutter widget types that host text input. Mapped to a class *name* that contains
# a token ``waypoints._is_input`` recognises ("textfield"), so inputs are treated as
# fields without the parser needing Flutter-specific knowledge.
_INPUT_WIDGETS = {"TextField", "TextFormField", "EditableText", "CupertinoTextField"}


def _class_for_widget(widget_type: str, editable: bool, password: bool) -> str:
    """Map a Flutter widget type to the class name the parser/waypoints key on.

    Inputs must contain "textfield" so ``waypoints._is_input`` recognises them (a
    password field additionally carries "securetextfield"); everything else keeps
    its real widget type (prefixed ``Flutter``) so the classifier and the screen
    fingerprint can still tell an ``ElevatedButton`` apart from a ``Text``.
    """
    if password:
        return "FlutterSecureTextField"
    if editable or widget_type in _INPUT_WIDGETS:
        return "FlutterTextField"
    return "Flutter" + (widget_type or "View").strip()


def _esc(s: str) -> str:
    """XML-escape an attribute value."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_flutter_screen(
    nodes: List[Dict[str, Any]], origin: Tuple[int, int] = (0, 0)
) -> Tuple[str, Dict[Tuple[int, int], int]]:
    """Render enumerated Flutter widgets as uiautomator XML + a ``center -> id`` map.

    ``nodes`` is the interactive widget set read from the Flutter integration server,
    each a dict with keys: ``i`` (stable id, used to map a tap back to its finder),
    ``type`` (widget type), ``key`` (``ValueKey`` value, the stable locator — ``""``
    if none), ``label`` (semantics label), ``text`` (visible text), ``editable`` /
    ``password`` / ``enabled`` (bools; ``enabled`` defaults true), and ``x``/``y``/
    ``w``/``h`` (on-screen rect).

    The ``ValueKey`` goes to ``resource-id`` (the locator field, like an Android
    resource-id) and the semantics label to ``content-desc``; the returned map lets a
    tap on ``element.center`` resolve back to the widget. ``origin`` offsets the rects
    (the coordinates only need to be internally consistent — tapping goes through the
    finder, not a device point). The ``<hierarchy>`` is marked ``mtr-flutter="1"`` so
    ``parse_screen`` tags the toolkit ``flutter`` and codegen wraps the steps as
    Flutter finders.
    """
    ox, oy = origin
    parts = ['<hierarchy rotation="0" mtr-flutter="1">']
    centers: Dict[Tuple[int, int], int] = {}
    for n in nodes:
        x1 = ox + int(n["x"])
        y1 = oy + int(n["y"])
        x2 = x1 + int(n["w"])
        y2 = y1 + int(n["h"])
        if x2 <= x1 or y2 <= y1:
            continue
        editable = bool(n.get("editable"))
        password = bool(n.get("password"))
        cls = _class_for_widget(str(n.get("type", "")), editable, password)
        # Matches CrawlElement.center exactly: (x1 + x2) // 2, (y1 + y2) // 2.
        centers[((x1 + x2) // 2, (y1 + y2) // 2)] = int(n["i"])
        parts.append(
            '<node class="%s" resource-id="%s" text="%s" content-desc="%s" '
            'bounds="[%d,%d][%d,%d]" clickable="true" focusable="%s" password="%s" enabled="%s"/>'
            % (
                cls,
                _esc(str(n.get("key", ""))),
                _esc(str(n.get("text", ""))),
                _esc(str(n.get("label", ""))),
                x1,
                y1,
                x2,
                y2,
                str(editable).lower(),
                str(password).lower(),
                str(n.get("enabled", True) is not False).lower(),
            )
        )
    parts.append("</hierarchy>")
    return "\n".join(parts), centers
