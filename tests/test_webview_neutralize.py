"""Neutralizing a lingering hidden WebView (device-free): via the standalone
neutralize_hidden_webviews and folded into web_snapshot(neutralize_hidden=True).
A hidden WebView is blanked (about:blank) so it stops wedging the native dump; a
visible one is left alone."""

from framework.crawler.webview import neutralize_hidden_webviews, web_snapshot


class _Switch:
    def __init__(self, drv):
        self.d = drv

    def context(self, name):
        self.d.context = name


class _Driver:
    def __init__(self, visibility="hidden", url="http://app/login", contexts=("NATIVE_APP", "WEBVIEW_x"), nodes=()):
        self.contexts = list(contexts)
        self.context = "NATIVE_APP"
        self.visibility = visibility
        self._url = url
        self.nodes = list(nodes)  # what the DOM enum returns ([] = no drivable content = hidden)
        self.navigated = []
        self.stopped = False
        self.switch_to = _Switch(self)

    @property
    def current_url(self):
        return self._url

    def execute_script(self, script, *args):
        if "querySelectorAll" in script:  # the interactive-DOM enum
            return list(self.nodes)
        if "visibilityState" in script:  # the visibility probe
            return self.visibility
        if "window.stop" in script:
            self.stopped = True
        return None

    def get(self, url):
        self.navigated.append(url)
        self._url = url


def test_hidden_webview_is_blanked():
    d = _Driver(visibility="hidden")
    assert neutralize_hidden_webviews(d) == 1
    assert d.navigated == ["about:blank"]
    assert d.stopped is True
    assert d.context == "NATIVE_APP"  # returned to native


def test_visible_webview_is_left_alone():
    d = _Driver(visibility="visible")
    assert neutralize_hidden_webviews(d) == 0
    assert d.navigated == []  # a real foreground web screen — don't touch it


def test_already_blank_is_skipped():
    d = _Driver(visibility="hidden", url="about:blank")
    assert neutralize_hidden_webviews(d) == 0
    assert d.navigated == []  # idempotent — no repeated navigation


def test_no_webview_context_is_noop():
    d = _Driver(contexts=("NATIVE_APP",))
    assert neutralize_hidden_webviews(d) == 0


def test_web_snapshot_neutralizes_hidden_in_place():
    # Hidden WebView, no drivable DOM: web_snapshot returns None but blanks it in
    # the same context switch it already made — no second contexts round-trip.
    d = _Driver(visibility="hidden", nodes=[])
    assert web_snapshot(d, neutralize_hidden=True) is None
    assert d.navigated == ["about:blank"]
    assert d.context == "NATIVE_APP"


def test_web_snapshot_leaves_hidden_alone_when_flag_off():
    # iOS path (neutralize_hidden=False): never blank the WebView.
    d = _Driver(visibility="hidden", nodes=[])
    assert web_snapshot(d, neutralize_hidden=False) is None
    assert d.navigated == []
