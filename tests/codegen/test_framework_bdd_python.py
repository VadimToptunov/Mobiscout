"""Python BDD suites (pytest-bdd, Behave) on the Page-Object framework: the senior-level BDD
contract as automated gates, for both platforms. The suites are EXECUTED against the fake app
in test_kit_execution.py."""

import py_compile
import re

import pytest

from framework.codegen.bdd_model import build_bdd_model
from framework.codegen.framework_bdd_python import render_behave, render_pytest_bdd
from framework.codegen.framework_model import build_framework_model
from framework.crawler.app_crawler import CrawlElement, CrawlResult, CrawlScreen
from framework.crawler.to_codegen import build_test_model

_RENDERERS = {"pytest_bdd": render_pytest_bdd, "behave": render_behave}


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


@pytest.fixture(params=["android", "ios"])
def platform(request):
    """Every gate runs for both platforms — one suite, two drivers."""
    return request.param


@pytest.fixture(params=sorted(_RENDERERS))
def flavour(request):
    """Both Python BDD runners."""
    return request.param


def _el(cls, text="", rid="", desc="", clk=True, platform="android"):
    ios = platform == "ios"
    return CrawlElement(
        resource_id=(rid if ios else f"com.x:id/{rid}") if rid else "",
        text=text,
        content_desc=desc,
        class_name=cls,
        clickable=clk,
        bounds=(0, 0, 300, 60),
        package="" if ios else "com.x",
    )


def _framework(platform):
    ios = platform == "ios"
    text, field, button = (
        ("StaticText", "TextField", "Button")
        if ios
        else ("android.widget.TextView", "android.widget.EditText", "android.widget.Button")
    )
    login = CrawlScreen(
        "login",
        [
            _el(text, "Welcome back", clk=False, platform=platform),
            _el(field, rid="email", desc="Email", platform=platform),
            _el(field, rid="password", desc="Password", platform=platform),
            _el(button, "Sign in", rid="signin", platform=platform),
        ],
        platform=platform,
    )
    catalog = CrawlScreen(
        "catalog",
        [
            _el(text, "Catalog", clk=False, platform=platform),
            _el(button, "Product", rid="prod", platform=platform),
            _el(button, "Back", rid="back", platform=platform),
        ],
        platform=platform,
    )
    settings = CrawlScreen(
        "settings",
        [_el(text, "Settings", clk=False, platform=platform), _el(button, "Back", rid="back", platform=platform)],
        platform=platform,
    )
    res = CrawlResult(screens={"login": login, "catalog": catalog, "settings": settings})
    res.transitions = [
        ("login", _el(button, "Sign in", rid="signin", platform=platform), "catalog"),
        ("catalog", _el(button, "Product", rid="prod", platform=platform), "settings"),
    ]
    model = build_test_model(res, app_package="com.x", app_activity=None if ios else ".Main")
    return build_framework_model(res, model, "com.x")


def _kit(platform, flavour):
    return _RENDERERS[flavour](_framework(platform))


def _features(files):
    return {p: c for p, c in files.items() if p.endswith(".feature")}


def _step_modules(files):
    return {p: c for p, c in files.items() if "steps/" in p and p.endswith("_steps.py")}


def _feature_steps(files):
    """Every step line of every feature, keyword stripped."""
    lines = "\n".join(_features(files).values()).splitlines()
    return [
        re.sub(r"^(Given|When|Then|And) ", "", ln.strip())
        for ln in lines
        if re.match(r"^\s+(Given|When|Then|And) ", ln)
    ]


def _patterns(files):
    """Every step pattern the step modules define (the decorator's string)."""
    source = "\n".join(_step_modules(files).values())
    return re.findall(r"""@(?:given|when|then)\((?:parsers\.parse\()?(["'])(.+?)\1""", source)


def _matches(pattern, line):
    regex = "^" + re.escape(pattern).replace(re.escape('"{value}"'), '"[^"]*"') + "$"
    return re.match(regex, line) is not None


def test_layout(platform, flavour):
    files = _kit(platform, flavour)
    assert _features(files) and _step_modules(files), sorted(files)
    assert "pages/base_page.py" in files and "requirements.txt" in files
    if flavour == "behave":
        assert "features/environment.py" in files and "conftest.py" not in files
        assert all(p.startswith("features/steps/") for p in _step_modules(files))
    else:
        assert "conftest.py" in files and "tests/test_features.py" in files
        assert 'scenarios("../features")' in files["tests/test_features.py"]


def test_features_are_declarative_no_locators_or_generic_steps(platform, flavour):
    for path, feature in _features(_kit(platform, flavour)).items():
        for smell in ("com.x:id", "UiSelector", "XCUIElementType", "xpath", "accessibility", 'I tap "', ' into "'):
            assert smell not in feature, f"{smell!r} in {path}:\n{feature}"


def test_reaching_a_screen_is_a_given_not_a_list_of_clicks(platform, flavour):
    catalog = _kit(platform, flavour)["features/catalog.feature"]
    assert "Given I am on the Catalog screen" in catalog, catalog
    assert "When I tap Sign in" not in catalog.split("Scenario: The catalog screen shows")[1], catalog


def test_background_holds_the_shared_precondition_once(platform, flavour):
    feature = _kit(platform, flavour)["features/welcome_back.feature"]
    assert "Background:\n    Given I am on the Welcome back screen" in feature, feature
    body = feature.split("Background:", 1)[1].split("Scenario", 1)[1]
    assert "Given I am on the Welcome back screen" not in body, feature
    for scenario in feature.split("  Scenario: ")[1:]:
        first = scenario.split("\n")[1].strip()
        assert first != "Then I see the Welcome back screen", "the Given already proves the screen is shown"
    assert "Then I am still on the Welcome back screen" in feature, "a rejected form must prove it stayed"


def test_every_step_has_exactly_one_definition_and_none_is_dead(platform, flavour):
    files = _kit(platform, flavour)
    patterns = [p for _, p in _patterns(files)]
    assert len(patterns) == len(set(patterns)), f"duplicate step definitions: {patterns}"
    lines = _feature_steps(files)
    for line in lines:
        hits = [p for p in patterns if _matches(p, line)]
        assert len(hits) == 1, f"{line!r} matches {hits}"
    for p in patterns:
        assert any(_matches(p, ln) for ln in lines), f"dead step definition: {p!r}"


def test_a_label_on_two_screens_gets_a_qualified_step(platform, flavour):
    patterns = [p for _, p in _patterns(_kit(platform, flavour))]
    back = [p for p in patterns if "Back" in p]
    assert all("screen" in p for p in back), back


def test_steps_are_one_call_on_a_page_object(platform, flavour):
    for path, source in _step_modules(_kit(platform, flavour)).items():
        for smell in ("AppiumBy", "find_element", "sleep(", "LOCATORS", "WebDriverWait"):
            assert smell not in source, f"{smell!r} in {path}"
        for body in re.split(r"\n@(?:given|when|then)\(", source)[1:]:
            statements = [ln for ln in body.split("\n")[2:] if ln.strip()]
            assert len(statements) == 1 and "Page(" in statements[0], body


def test_every_file_compiles(platform, flavour, tmp_path):
    for rel, content in _kit(platform, flavour).items():
        if rel.endswith(".py"):
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            py_compile.compile(str(path), doraise=True)


def test_scenarios_differing_only_in_data_become_one_outline(platform):
    fm = _framework(platform)
    welcome = fm.pages[0].name
    src = next(sc for sc in fm.scenarios if sc.group == welcome and any(c.op == "enter" for c in sc.calls))
    twin = type(src)(
        name=f"{src.name}_again",
        description=f"{src.description} Again.",
        calls=[type(c)(c.page, c.op, c.element, "other@x" if c.op == "enter" else c.value) for c in src.calls],
        group=src.group,
    )
    fm.scenarios.append(twin)
    feature = next(f for f in build_bdd_model(fm).features if f.page == welcome)
    outlines = [sc for sc in feature.scenarios if sc.examples]
    assert len(outlines) == 1, feature
    columns, rows = outlines[0].examples
    assert len(rows) == 2 and all(any("<" + c + ">" in s.text for s in outlines[0].steps) for c in columns)
