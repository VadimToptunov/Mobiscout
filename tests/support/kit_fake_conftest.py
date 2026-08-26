"""A self-contained pytest conftest that lets a *generated* Appium kit run with no device.

Copied into a temp dir next to an emitted kit; on import (conftest loads before any test
is collected) it replaces `appium` / `selenium` in ``sys.modules`` with fakes backed by a
screen state-machine loaded from ``$MOBISCOUT_FAKE_APP`` (a JSON model). The kit then runs
through real pytest — find_element/click/send_keys/is_displayed all resolve against the
model — so "the generated tests pass" becomes an executed claim, not a `py_compile` guess.

The model is derived from the CrawlResult independently of the emitter, so a codegen bug
(asserting an element on a screen the flow never reached, e.g. a missing auth/scroll step)
surfaces as a real NoSuchElementException failure.

Model JSON: {"start": int, "screens": [[[by, value], ...], ...],
             "transitions": [[from_idx, by, value, to_idx], ...],
             "reveals": [[screen_idx, by, value], ...]}  # revealed only after a scroll
"""

import json
import os
import sys
import types


# --- exceptions -------------------------------------------------------------
class NoSuchElementException(Exception):
    pass


class TimeoutException(Exception):
    pass


class WebDriverException(Exception):
    """Selenium's base driver error. The kit catches it to ride out a transient
    "Timed out waiting for the root AccessibilityNodeInfo" from an animating screen, so
    the stub has to expose it or the emitted module won't even import."""

    pass


# --- AppiumBy (real wire strings, so model keys match the kit's find_element) ---
class AppiumBy:
    ID = "id"
    ACCESSIBILITY_ID = "accessibility id"
    XPATH = "xpath"
    CLASS_NAME = "class name"
    NAME = "name"
    ANDROID_UIAUTOMATOR = "-android uiautomator"
    IOS_PREDICATE = "-ios predicate string"
    IOS_CLASS_CHAIN = "-ios class chain"


class _Options:
    """Accepts every `options.x = y` and `set_capability` the generated setup makes."""

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)

    def set_capability(self, k, v):
        pass


class _Element:
    def __init__(self, driver, by, value):
        self._driver, self._by, self._value = driver, by, value
        self.id = f"{by}:{value}"

    def click(self):
        self._driver._apply_transition(self._by, self._value)

    def send_keys(self, *args, **_k):
        self._driver._typed[(self._by, self._value)] = str(args[0]) if args else ""

    def clear(self):
        pass

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    @property
    def text(self):
        return ""


class _Driver:
    def __init__(self, model):
        self._screens = [{tuple(loc) for loc in scr} for scr in model.get("screens", [])]
        self._transitions = {(t[0], t[1], t[2]): t[3] for t in model.get("transitions", [])}
        self._reveals = {}
        for r in model.get("reveals", []):
            self._reveals.setdefault(r[0], set()).add((r[1], r[2]))
        self._start = model.get("start", 0)
        self._revealed = set()  # (screen, by, value) unlocked by a scroll
        self._typed = {}  # (by, value) -> text, to model input validation
        self.current = self._start

    # navigation
    def _valid_input(self):
        """Model a validating form: a submit only advances when what was typed is
        plausible. Enough for negative-case tests (invalid input must stay on the form)
        to diverge from positive journeys without a full form spec."""
        for (_by, value), text in self._typed.items():
            v = str(value).lower()
            if ("email" in v or "mail" in v) and "@" not in text:
                return False
            if "password" in v and len(text) < 4:
                return False
        return True

    def _apply_transition(self, by, value):
        nxt = self._transitions.get((self.current, by, value))
        if nxt is not None and self._valid_input():
            self.current = nxt
            self._typed.clear()

    def _present(self, by, value):
        if (by, value) in self._screens[self.current]:
            return True
        return (self.current, by, value) in self._revealed

    # webdriver surface used by generated kits
    def activate_app(self, *_a, **_k):
        self.current = self._start
        self._revealed.clear()
        self._typed.clear()

    def find_element(self, by, value):
        if self._present(by, value):
            return _Element(self, by, value)
        raise NoSuchElementException(f"{by}={value} not on screen {self.current}")

    def find_elements(self, by, value):
        return [_Element(self, by, value)] if self._present(by, value) else []

    def execute_script(self, name, *args):
        # A scroll reveals this screen's below-the-fold elements.
        if "scroll" in str(name).lower():
            for loc in self._reveals.get(self.current, ()):
                self._revealed.add((self.current, loc[0], loc[1]))
        return None

    def press_keycode(self, *_a, **_k):
        pass

    def back(self):
        pass

    def get_window_size(self):
        return {"width": 1080, "height": 1920}

    def quit(self):
        pass


class _WebDriverWait:
    def __init__(self, driver, timeout=0, poll_frequency=0.0, *_a, **_k):
        self._driver = driver

    def until(self, method, message=""):
        last = None
        for _ in range(5):
            try:
                value = method(self._driver)
            except NoSuchElementException as exc:
                last = exc
                continue
            if value:
                return value
        raise TimeoutException(message or (str(last) if last else "condition not met"))


def _install(model):
    driver_holder = {"model": model}

    def _remote(*_a, **_k):
        return _Driver(driver_holder["model"])

    appium = types.ModuleType("appium")
    appium_webdriver = types.ModuleType("appium.webdriver")
    appium_webdriver.Remote = _remote
    appium.webdriver = appium_webdriver
    common = types.ModuleType("appium.webdriver.common")
    appiumby = types.ModuleType("appium.webdriver.common.appiumby")
    appiumby.AppiumBy = AppiumBy
    opts_android = types.ModuleType("appium.options.android")
    opts_android.UiAutomator2Options = _Options
    opts_ios = types.ModuleType("appium.options.ios")
    opts_ios.XCUITestOptions = _Options

    sel = types.ModuleType("selenium")
    sel_common = types.ModuleType("selenium.common")
    sel_exc = types.ModuleType("selenium.common.exceptions")
    sel_exc.NoSuchElementException = NoSuchElementException
    sel_exc.TimeoutException = TimeoutException
    sel_exc.WebDriverException = WebDriverException
    sel_wd = types.ModuleType("selenium.webdriver")
    sel_support = types.ModuleType("selenium.webdriver.support")
    sel_ui = types.ModuleType("selenium.webdriver.support.ui")
    sel_ui.WebDriverWait = _WebDriverWait

    for name, mod in {
        "appium": appium,
        "appium.webdriver": appium_webdriver,
        "appium.webdriver.common": common,
        "appium.webdriver.common.appiumby": appiumby,
        "appium.options": types.ModuleType("appium.options"),
        "appium.options.android": opts_android,
        "appium.options.ios": opts_ios,
        "selenium": sel,
        "selenium.common": sel_common,
        "selenium.common.exceptions": sel_exc,
        "selenium.webdriver": sel_wd,
        "selenium.webdriver.support": sel_support,
        "selenium.webdriver.support.ui": sel_ui,
    }.items():
        sys.modules[name] = mod


with open(os.environ["MOBISCOUT_FAKE_APP"], encoding="utf-8") as _f:
    _install(json.load(_f))
