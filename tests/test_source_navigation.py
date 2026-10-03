"""Tests from SOURCE reach each screen before checking it (#313): the analyzers find the
control that navigates (Android navigate() in a Button / .clickable; SwiftUI NavigationLink in
its three forms, .sheet) and the screen the app opens on, and every non-entry case taps its way
there from the entry screen — falling back to launch-only, saying why, when no path is known."""

import py_compile
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from framework.analyzers.android_analyzer import AndroidAnalyzer
from framework.analyzers.ios_source_analyzer import IOSSourceAnalyzer
from framework.codegen import get_emitter
from framework.codegen.app_model_adapter import build_smoke_model
from framework.codegen.ir import ActionType
from framework.codegen.source_app_model import source_smoke_inputs

FIXTURES = Path(__file__).parent / "fixtures" / "source_navigation"


def _app(tmp_path, name):
    root = tmp_path / name
    root.mkdir()
    shutil.copy(FIXTURES / name, root / name)
    return root


@pytest.fixture
def android(tmp_path):
    return _app(tmp_path, "App.kt")


@pytest.fixture
def ios(tmp_path):
    return _app(tmp_path, "App.swift")


def _edges(result):
    return {(n.from_screen, n.to_screen): (n.trigger, n.trigger_test_tag) for n in result.navigation if n.from_screen}


def test_android_finds_the_navigating_controls_and_the_start_destination(android):
    result = AndroidAnalyzer().analyze(str(android))
    assert result.entry_screen == "home"
    edges = _edges(result)
    assert edges[("HomeScreen", "details")] == ("Details", "open_details")  # Button(onClick) { Text }
    assert edges[("HomeScreen", "settings")] == ("Settings", None)  # Text(.., Modifier.clickable { })


def test_ios_finds_every_navigation_link_form_the_sheet_and_the_window_root(ios):
    result = IOSSourceAnalyzer().analyze(str(ios))
    assert result.entry_screen == "HomeView"
    edges = _edges(result)
    assert edges[("HomeView", "DetailsView")] == ("Details", "open_details")  # (destination:) { Text } + identifier
    assert edges[("HomeView", "ProfileView")] == ("Profile", None)  # ("Profile", destination:)
    assert edges[("HomeView", "OrdersView")] == ("Orders", None)  # { dest } label: { Text }
    assert edges[("HomeView", "SettingsView")] == (None, None)  # .sheet — its trigger is a separate Button


@pytest.mark.parametrize("app, screen", [("android", "detailsscreen"), ("ios", "detailsview")])
def test_a_non_entry_case_taps_its_way_there_before_checking(app, screen, request):
    model, paths = source_smoke_inputs(str(request.getfixturevalue(app)))
    case = next(c for c in build_smoke_model(model, "com.x", paths=paths).cases if c.name == screen)
    actions = [s.action for s in case.steps]
    assert actions[:2] == [ActionType.LAUNCH, ActionType.TAP], case.steps
    assert actions.index(ActionType.ASSERT) > actions.index(ActionType.TAP)
    assert "open_details" in case.steps[1].selector.value


def test_a_screen_with_no_known_path_keeps_launch_only_and_says_why(ios):
    model, paths = source_smoke_inputs(str(ios))
    case = next(c for c in build_smoke_model(model, "com.x", paths=paths).cases if c.name == "settingsview")
    assert ActionType.TAP not in [s.action for s in case.steps]
    assert "no known path from HomeView" in case.steps[0].description


def test_without_navigation_data_the_old_launch_only_cases_are_unchanged(android):
    model, _ = source_smoke_inputs(str(android))
    for case in build_smoke_model(model, "com.x").cases:
        assert [s.action for s in case.steps][0] is ActionType.LAUNCH
        assert ActionType.TAP not in [s.action for s in case.steps]


@pytest.mark.parametrize("app", ["android", "ios"])
def test_generate_tests_from_source_emits_navigating_cases_that_compile(app, request, tmp_path):
    from framework.cli.generate_commands import generate

    out = tmp_path / "out"
    result = CliRunner().invoke(
        generate,
        ["tests", "--source", str(request.getfixturevalue(app)), "--app-package", "com.x", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    sources = list(out.rglob("*.py"))
    assert sources, result.output
    for path in sources:
        py_compile.compile(str(path), doraise=True)
    code = "\n".join(p.read_text(encoding="utf-8") for p in sources)
    assert "open_details" in code and ".click()" in code, code


def test_every_emitter_renders_the_navigating_cases(android):
    model, paths = source_smoke_inputs(str(android))
    test_model = build_smoke_model(model, "com.x", paths=paths)
    for target in ("python_pytest", "java_testng", "kotlin_appium", "js_webdriverio"):
        assert "open_details" in "\n".join(get_emitter(target).emit(test_model).values()), target
