"""Capricious devices are the norm, not the exception: apps hang (ANR dialogs),
cold-start slowly (blank first dumps), and pop system prompts over the app. The
crawler must recover and still map real content, not return an empty kit. These
tests model exactly those conditions with fake drivers."""

from framework.crawler.app_crawler import AppCrawler

_PKG = "com.example.app"


def _node(cls, text="", pkg=_PKG, clickable=True, x=0, y=0, w=200, h=80, desc=""):
    # content-desc is part of the structural fingerprint (text is not), so distinct
    # screens in these fixtures differ by desc to get distinct fingerprints.
    return (
        f'<node class="{cls}" text="{text}" content-desc="{desc}" resource-id="" '
        f'package="{pkg}" clickable="{"true" if clickable else "false"}" '
        f'bounds="[{x},{y}][{x + w},{y + h}]" />'
    )


def _hierarchy(*nodes):
    return f'<?xml version="1.0"?><hierarchy rotation="0">{"".join(nodes)}</hierarchy>'


# App's real first screen — two of its own buttons.
_APP_SCREEN = _hierarchy(
    _node("android.widget.Button", "Transfer", x=0, y=100),
    _node("android.widget.Button", "Markets", x=0, y=200),
)


class FakeANRDriver:
    """The app is foreground but a system ANR dialog ("… isn't responding: Wait /
    Close app", package 'android') covers it. Tapping Wait dismisses it to the app."""

    def __init__(self):
        self._cleared = False

    def page_source(self):
        if self._cleared:
            return _APP_SCREEN
        # ANR overlay: foreign-package system buttons, none of the app's own content.
        return _hierarchy(
            _node("android.widget.Button", "Wait", pkg="android", x=0, y=900),
            _node("android.widget.Button", "Close app", pkg="android", x=210, y=900),
        )

    def tap(self, x, y):
        # Tapping the "Wait" button (left, y~900) clears the ANR.
        if not self._cleared and y >= 880 and x < 200:
            self._cleared = True

    def back(self):
        pass

    def current_package(self):
        return _PKG  # the app is the resumed activity, behind the dialog


class FakeSlowLaunchDriver:
    """A slow cold start: the first few UI dumps come back empty (splash / not yet
    rendered); refresh() waits and eventually returns the real content."""

    def __init__(self, blanks=2):
        self._reads = 0
        self._blanks = blanks

    def _dump(self):
        self._reads += 1
        return _APP_SCREEN if self._reads > self._blanks else _hierarchy()

    def page_source(self):
        return self._dump()

    def refresh(self, wait=0):
        return self._dump()

    def tap(self, x, y):
        pass

    def back(self):
        pass

    def current_package(self):
        return _PKG


def test_recovers_from_an_anr_dialog_and_maps_the_app():
    driver = FakeANRDriver()
    result = AppCrawler(driver, _PKG, max_steps=20, max_depth=4).crawl()
    # It must have cleared the ANR and mapped the app's real screen (not the dialog).
    assert result.screens
    labels = {e.text for s in result.screens.values() for e in s.elements}
    assert "Transfer" in labels and "Markets" in labels
    assert "Close app" not in labels  # the ANR dialog is not what we mapped


def test_recovers_from_a_blank_slow_launch():
    driver = FakeSlowLaunchDriver(blanks=2)
    result = AppCrawler(driver, _PKG, max_steps=20, max_depth=4).crawl()
    assert result.screens  # retried through the blank dumps instead of giving up
    labels = {e.text for s in result.screens.values() for e in s.elements}
    assert "Transfer" in labels


_HOME = _hierarchy(_node("android.widget.Button", "Go", x=0, y=100, desc="home.go"))
_DETAIL = _hierarchy(_node("android.widget.Button", "Confirm", x=0, y=100, desc="detail.confirm"))


class FakeDumpRaceDriver:
    """A tap navigates, but the first UI dump of the new screen races back empty;
    refresh() (wait + re-read) then returns the real content."""

    def __init__(self):
        self.state = "home"

    def page_source(self):
        if self.state == "home":
            return _HOME
        if self.state == "detail_blank":
            return _hierarchy()  # racing empty dump
        return _DETAIL

    def tap(self, x, y):
        if self.state == "home" and y < 200:  # tapped "Go"
            self.state = "detail_blank"

    def refresh(self, wait=0):
        if self.state == "detail_blank":
            self.state = "detail"  # the tree finishes building
        return self.page_source()

    def back(self):
        pass

    def current_package(self):
        return _PKG


class FakeDriftDriver:
    """A tap sends the app to the background (a foreign app takes over); Back won't
    bring it back — only re-launching does."""

    def __init__(self):
        self.foreign = False
        self.launches = 0

    def page_source(self):
        if self.foreign:
            return _hierarchy(_node("android.widget.TextView", "Other app", pkg="com.other", clickable=False))
        return _hierarchy(_node("android.widget.Button", "Leave", x=0, y=100))

    def tap(self, x, y):
        if not self.foreign and y < 200:  # tapped "Leave" -> drifts away
            self.foreign = True

    def back(self):
        pass  # the foreign app ignores Back

    def launch(self, package):
        self.launches += 1
        self.foreign = False
        return True

    def current_package(self):
        return "com.other" if self.foreign else _PKG


def test_reads_through_a_racing_empty_dump():
    driver = FakeDumpRaceDriver()
    result = AppCrawler(driver, _PKG, max_steps=20, max_depth=4).crawl()
    labels = {e.text for s in result.screens.values() for e in s.elements}
    assert "Confirm" in labels  # the navigated screen was mapped despite the race


def test_relaunches_when_the_app_drifts_to_the_background():
    driver = FakeDriftDriver()
    result = AppCrawler(driver, _PKG, max_steps=20, max_depth=4).crawl()
    assert driver.launches >= 1  # re-launched instead of getting stuck on the foreign app
    assert result.screens  # and still produced a map of the app
