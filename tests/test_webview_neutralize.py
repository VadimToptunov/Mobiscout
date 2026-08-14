"""neutralize_hidden_webviews (device-free): a lingering hidden WebView is blanked
(about:blank) so it stops wedging the native dump; a visible one is left alone."""

from framework.crawler.webview import neutralize_hidden_webviews


class _Switch:
    def __init__(self, drv):
        self.d = drv

    def context(self, name):
        self.d.context = name


class _Driver:
    def __init__(self, visibility="hidden", url="http://app/login", contexts=("NATIVE_APP", "WEBVIEW_x")):
        self.contexts = list(contexts)
        self.context = "NATIVE_APP"
        self.visibility = visibility
        self._url = url
        self.navigated = []
        self.stopped = False
        self.switch_to = _Switch(self)

    @property
    def current_url(self):
        return self._url

    def execute_script(self, script, *args):
        if "visibilityState" in script:
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
