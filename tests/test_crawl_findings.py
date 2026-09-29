"""The crawl records the defects it runs into — a tap that crashes the app, a tap that leads
to a generic error screen — and codegen turns each into a test that reproduces it: red while
the bug is there, green once it is fixed."""

from framework.codegen.framework_model import build_framework_model
from framework.crawler.app_crawler import AppCrawler
from framework.crawler.to_codegen import build_test_model

APP = "com.example.shop"
LAUNCHER = "com.google.android.apps.nexuslauncher"


def _node(label, rid, clickable, bounds, cls="android.widget.Button"):
    x1, y1, x2, y2 = bounds
    return (
        f'<node class="{cls}" package="{APP}" resource-id="{APP}:id/{rid}" text="{label}" '
        f'content-desc="" clickable="{"true" if clickable else "false"}" '
        f'bounds="[{x1},{y1}][{x2},{y2}]"/>'
    )


def _screen(*nodes):
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


SCREENS = {
    "shop": _screen(
        _node("Shop", "title", False, (0, 0, 300, 40), cls="android.widget.TextView"),
        _node("Refresh", "refresh", True, (0, 50, 300, 100)),
        _node("Orders", "orders", True, (0, 110, 300, 160)),
        _node("Terms", "terms", True, (0, 170, 300, 220)),
    ),
    "orders": _screen(
        _node("Orders", "orders_title", False, (0, 0, 300, 40), cls="android.widget.TextView"),
        _node("Something went wrong", "error", False, (0, 50, 300, 100), cls="android.widget.TextView"),
    ),
}
LAUNCHER_SCREEN = (
    '<hierarchy rotation="0"><node class="android.widget.FrameLayout" package="' + LAUNCHER + '"/></hierarchy>'
)
BROWSER_SCREEN = (
    '<hierarchy rotation="0"><node class="android.webkit.WebView" package="com.android.chrome"/></hierarchy>'
)


class CrashyDriver:
    """Refresh crashes the app to the home screen; Orders opens a generic error; Terms opens the
    browser (a hand-off, not a defect)."""

    def __init__(self):
        self.current, self.pkg, self.nav = "shop", APP, []

    def page_source(self):
        if self.pkg == LAUNCHER:
            return LAUNCHER_SCREEN
        if self.pkg != APP:
            return BROWSER_SCREEN
        return SCREENS[self.current]

    def current_package(self):
        return self.pkg

    def back(self):
        self.pkg = APP
        if self.nav:
            self.current = self.nav.pop()

    def launch(self, _package):
        self.pkg, self.current, self.nav = APP, "shop", []

    def tap(self, x, y):
        if self.current != "shop":
            return
        label = {75: "Refresh", 135: "Orders", 195: "Terms"}.get(y)
        if label == "Refresh":
            self.pkg = LAUNCHER
        elif label == "Orders":
            self.nav.append(self.current)
            self.current = "orders"
        elif label == "Terms":
            self.pkg = "com.android.chrome"


def _crawl():
    return AppCrawler(CrashyDriver(), APP, max_steps=40).crawl()


def test_a_crash_and_an_error_screen_are_findings_a_hand_off_is_not():
    findings = _crawl().findings
    kinds = {(f.kind, f.element.label) for f in findings}
    assert ("crash", "Refresh") in kinds, findings
    assert ("error_screen", "Orders") in kinds, findings
    assert not any(f.element.label == "Terms" for f in findings), "opening the browser is not a defect"
    error = next(f for f in findings if f.kind == "error_screen")
    assert error.evidence == "Something went wrong"


def test_each_finding_becomes_a_defect_scenario_that_checks_the_app_survived():
    result = _crawl()
    model = build_test_model(result, app_package=APP, app_activity=".Main")
    fm = build_framework_model(result, model, APP)
    defects = [sc for sc in fm.scenarios if sc.defect]
    ops = {sc.calls[-1].op for sc in defects}
    assert ops == {"app_running", "lacks"}, [(sc.name, sc.calls) for sc in defects]
    for sc in defects:
        assert sc.calls[-2].op == "tap", sc.calls
        assert "fails until it is fixed" in sc.description and sc.title in sc.description


def _kit(result, tmp_path):
    """The generated pytest framework, wired to the device-free fake app."""
    from framework.crawler.page_kit import build_framework_kit
    from tests.codegen.test_kit_execution import _CONFTEST

    model = build_test_model(result, app_package=APP, app_activity=".Main")
    kit = tmp_path / "kit"
    for rel, content in build_framework_kit(result, model, APP).items():
        path = kit / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    conftest = kit / "conftest.py"
    conftest.write_text(
        _CONFTEST.read_text(encoding="utf-8") + "\n\n" + conftest.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return kit


def _app(result, crashes=True, error_shown=True):
    """The fake app from the crawl: the Refresh tap crashes it (unless fixed), and the Orders
    screen shows its error (unless fixed)."""
    from tests.codegen.test_kit_execution import _chain, _fake_app
    from framework.crawler.to_codegen import _owned, selector_for

    app = _fake_app(result, APP)
    fps = list(result.screens)
    for f in result.findings:
        screen = result.screens[f.src]
        sel = selector_for(f.element, _owned(screen, APP), screen.platform)
        if f.kind == "crash" and crashes:
            app.setdefault("crashes", []).extend([fps.index(f.src), by, v] for by, v in _chain(sel, "android"))
        if f.kind == "error_screen" and not error_shown:
            dst = result.screens[f.dst]
            owned = _owned(dst, APP)
            err = next(e for e in owned if f.evidence in e.text)
            gone = set(_chain(selector_for(err, owned, dst.platform), "android"))
            idx = fps.index(f.dst)
            app["screens"][idx] = [loc for loc in app["screens"][idx] if tuple(loc) not in gone]
    return app


def test_defect_tests_are_red_while_the_bug_is_there_and_green_once_fixed(tmp_path):
    from tests.codegen.test_kit_execution import _run_pytest

    result = _crawl()
    kit = _kit(result, tmp_path)
    tests = "\n".join(p.read_text(encoding="utf-8") for p in (kit / "tests").glob("test_*.py"))
    assert tests.count("@pytest.mark.defect") == 2 and "is_app_running()" in tests, tests

    buggy = _run_pytest(kit, _app(result), verbose=True)
    assert buggy.returncode != 0, buggy.stdout
    failed = [ln for ln in buggy.stdout.splitlines() if ln.startswith("FAILED")]
    assert len(failed) == 2 and all("defect_" in ln for ln in failed), buggy.stdout

    fixed = _run_pytest(kit, _app(result, crashes=False, error_shown=False), verbose=True)
    assert fixed.returncode == 0, f"defect tests must pass once the bugs are fixed:\n{fixed.stdout}\n{fixed.stderr}"


def test_every_language_marks_its_defect_tests_and_checks_the_app_survived():
    from framework.crawler.page_kit import FRAMEWORK_ONLY_TARGETS, build_target_framework

    result = _crawl()
    model = build_test_model(result, app_package=APP, app_activity=".Main")
    marks = {
        "python_pytest": ("@pytest.mark.defect", "is_app_running()"),
        "python_pytest_bdd": ("@defect", "is_app_running()"),
        "python_behave": ("@defect", "is_app_running()"),
        "java_testng": ('@Test(groups = "defect")', "isAppRunning()"),
        "java_cucumber": ("@defect", "isAppRunning()"),
        "kotlin_appium": ('@Tag("defect")', "isAppRunning()"),
        "kotlin_cucumber": ("@defect", "isAppRunning()"),
        "js_webdriverio": ("@defect", "isAppRunning()"),
        "js_cucumber": ("@defect", "isAppRunning()"),
    }
    assert set(FRAMEWORK_ONLY_TARGETS) <= set(marks)
    for target, (mark, check) in marks.items():
        kit = build_target_framework(target, result, model, APP) or {}
        source = "\n".join(kit.values())
        assert source.count(mark) >= 2, f"{target}: both defects must carry {mark!r}"
        assert check in source, f"{target}: the crash test must check the app survived"
        if "cucumber" in target or "bdd" in target or "behave" in target:
            assert "Then the app is still running" in source, target


def test_the_kit_reports_the_defects(tmp_path):
    from framework.crawler.pipeline import run_kit

    summary = run_kit({"package": APP, "output": str(tmp_path), "max_steps": 40}, driver=CrashyDriver())
    assert summary["defects"] == 2
    report = (tmp_path / "defects.md").read_text(encoding="utf-8")
    assert "**Refresh**" in report and "crashes the app" in report
    assert "**Orders**" in report and "Something went wrong" in report
