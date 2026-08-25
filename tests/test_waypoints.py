"""Waypoints: the crawler passes gates (login/OTP/permission/biometric) to reach
the screens behind them. Driven with a recording fake driver — device-free."""

from framework.crawler.app_crawler import AppCrawler, CrawlElement, CrawlScreen
from framework.crawler.waypoints import Waypoint, apply_first_match, matches


class RecordingDriver:
    """Records tap/type/back and serves a scripted sequence of page sources."""

    def __init__(self, pages):
        self._pages = list(pages)
        self._i = 0
        self.calls = []

    def page_source(self):
        return self._pages[min(self._i, len(self._pages) - 1)]

    def tap(self, x, y):
        self.calls.append(("tap", x, y))
        self._i = min(self._i + 1, len(self._pages) - 1)

    def type_text(self, text):
        self.calls.append(("type", text))

    def back(self):
        self.calls.append(("back",))

    def current_package(self):
        return "com.x"


def _el(cls, text="", rid="", desc=""):
    return CrawlElement(
        resource_id=rid,
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=True,
        bounds=(0, 0, 100, 40),
        package="com.x",
    )


def _login_screen():
    return CrawlScreen(
        "login",
        [
            _el("android.widget.EditText", rid="email", desc="Email"),
            _el("android.widget.EditText", rid="password", desc="Password"),
            _el("android.widget.Button", text="Sign in", rid="signin"),
        ],
        platform="android",
    )


def test_matches_by_text_and_input():
    s = _login_screen()
    assert matches(Waypoint(when={"text_contains": "sign in"}, action="fill"), s)
    assert matches(Waypoint(when={"has_input": True}, action="fill"), s)
    assert not matches(Waypoint(when={"text_contains": "checkout"}, action="fill"), s)


def test_fill_waypoint_types_credentials_and_taps_submit():
    driver = RecordingDriver(["<hierarchy/>"])
    wp = Waypoint(
        when={"text_contains": "sign in"},
        action="fill",
        data={"fields": {"email": "test@example.com", "password": "Pw123!"}, "submit": "Sign in"},
    )
    assert apply_first_match([wp], driver, _login_screen())
    typed = [c[1] for c in driver.calls if c[0] == "type"]
    assert "test@example.com" in typed and "Pw123!" in typed
    assert ("tap", 50, 20) in driver.calls  # submit tapped (element center)


def test_fill_unmatched_fields_go_to_different_inputs():
    # Two fields whose hints match NEITHER input must be consumed positionally into
    # two DISTINCT inputs — not both overwriting inputs[0] (the old fallback bug).
    screen = CrawlScreen(
        "form",
        [
            CrawlElement("f1", "", "", "android.widget.EditText", True, (0, 0, 100, 40), package="com.x"),
            CrawlElement("f2", "", "", "android.widget.EditText", True, (0, 60, 100, 100), package="com.x"),
        ],
        platform="android",
    )
    driver = RecordingDriver(["<hierarchy/>"])
    wp = Waypoint(when={"has_input": True}, action="fill", data={"fields": {"alpha": "A", "beta": "B"}})
    assert apply_first_match([wp], driver, screen)
    taps = [(c[1], c[2]) for c in driver.calls if c[0] == "tap"]
    typed = [c[1] for c in driver.calls if c[0] == "type"]
    assert typed == ["A", "B"]
    assert taps == [(50, 20), (50, 80)]  # two different input centers, not the same one twice
    assert len(set(taps)) == 2


def test_totp_waypoint_enters_current_code():
    otp_screen = CrawlScreen(
        "otp",
        [
            _el("android.widget.EditText", rid="otp", desc="One-time code"),
            _el("android.widget.Button", text="Verify", rid="verify"),
        ],
        platform="android",
    )
    driver = RecordingDriver(["<hierarchy/>"])
    wp = Waypoint(
        when={"text_contains": "one-time"},
        action="totp",
        data={"secret": "JBSWY3DPEHPK3PXP", "field": "otp", "submit": "Verify"},
    )
    assert apply_first_match([wp], driver, otp_screen)
    typed = [c[1] for c in driver.calls if c[0] == "type"]
    assert len(typed) == 1 and typed[0].isdigit() and len(typed[0]) == 6  # a TOTP code


def test_totp_waypoint_without_secret_is_skipped_not_crash():
    # A misconfigured TOTP waypoint (no "secret") must be skipped, not raise a KeyError
    # up out of the crawl and end it.
    otp_screen = CrawlScreen(
        "otp",
        [_el("android.widget.EditText", rid="otp", desc="One-time code")],
        platform="android",
    )
    driver = RecordingDriver(["<hierarchy/>"])
    wp = Waypoint(when={"text_contains": "one-time"}, action="totp", data={"field": "otp"})
    assert apply_first_match([wp], driver, otp_screen) is False
    assert not any(c[0] == "type" for c in driver.calls)  # nothing typed


def test_grant_waypoint_taps_allow_not_dont_allow():
    # A permission dialog lists "Don't Allow" then "Allow". "allow" is a substring of
    # BOTH, so a plain substring finder taps the deny button — the grant must tap Allow.
    deny = CrawlElement("deny", "Don't Allow", "", "android.widget.Button", True, (0, 0, 100, 40), package="com.x")
    allow = CrawlElement("allow", "Allow", "", "android.widget.Button", True, (0, 100, 100, 140), package="com.x")
    screen = CrawlScreen("perm", [deny, allow], platform="android")
    driver = RecordingDriver(["<hierarchy/>"])
    wp = Waypoint(when={"text_contains": "allow"}, action="grant")
    assert apply_first_match([wp], driver, screen)
    taps = [c for c in driver.calls if c[0] == "tap"]
    assert taps == [("tap", 50, 120)]  # center of "Allow" (y 100..140), never "Don't Allow" (y 0..40)


def test_crawler_passes_gate_and_reaches_screen_behind():
    # Page 0: login (gate). After the waypoint taps submit, page 1: the home screen.
    login_xml = (
        '<hierarchy><node class="android.widget.EditText" resource-id="email" text="" '
        'content-desc="Email" clickable="true" bounds="[0,0][100,40]" package="com.x"/>'
        '<node class="android.widget.Button" resource-id="signin" text="Sign in" '
        'clickable="true" bounds="[0,50][100,90]" package="com.x"/></hierarchy>'
    )
    home_xml = (
        '<hierarchy><node class="android.widget.TextView" resource-id="welcome" text="Welcome home" '
        'clickable="false" bounds="[0,0][200,40]" package="com.x"/></hierarchy>'
    )
    driver = RecordingDriver([login_xml, home_xml])
    wp = Waypoint(
        when={"text_contains": "sign in"}, action="fill", data={"fields": {"email": "a@b.com"}, "submit": "Sign in"}
    )
    result = AppCrawler(driver, "com.x", max_steps=5, waypoints=[wp]).crawl()
    # The home screen (behind the gate) is now part of the crawl.
    assert any("welcome" in " ".join(e.resource_id for e in s.elements) for s in result.screens.values())
    assert any(c[0] == "type" for c in driver.calls)  # the gate was filled


def test_pipeline_run_kit_applies_config_waypoints(tmp_path, monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")
    from framework.crawler.pipeline import run_kit

    login_xml = (
        '<hierarchy><node class="android.widget.EditText" resource-id="email" content-desc="Email" '
        'clickable="true" bounds="[0,0][100,40]" package="com.x"/>'
        '<node class="android.widget.Button" resource-id="signin" text="Sign in" '
        'clickable="true" bounds="[0,50][100,90]" package="com.x"/></hierarchy>'
    )
    home_xml = (
        '<hierarchy><node class="android.widget.Button" resource-id="home" text="Home" '
        'clickable="true" bounds="[0,0][100,40]" package="com.x"/></hierarchy>'
    )
    driver = RecordingDriver([login_xml, home_xml])
    run_kit(
        {
            "package": "com.x",
            "targets": ["python_pytest"],
            "output": str(tmp_path),
            "waypoints": [
                {
                    "when": {"text_contains": "sign in"},
                    "action": "fill",
                    "data": {"fields": {"email": "a@b.com"}, "submit": "Sign in"},
                }
            ],
        },
        driver=driver,
    )
    assert any(c[0] == "type" for c in driver.calls)  # config waypoint -> gate filled
