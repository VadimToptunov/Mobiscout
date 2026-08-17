"""Hybrid WebView in generated tests (device-free): a WebView-served screen's
assertions are wrapped in a native<->web context switch in the model, and the
python/Appium emitter renders the switch."""

from framework.codegen import get_emitter
from framework.codegen.ir import ActionType
from framework.crawler.app_crawler import parse_screen
from framework.crawler.models import CrawlResult
from framework.crawler.to_codegen import build_test_model

_WEB = (
    '<hierarchy rotation="0" mtr-web="1">'
    '<node class="android.widget.Button" resource-id="id/buy" text="Buy" content-desc="" '
    'clickable="true" bounds="[0,0][100,50]"/></hierarchy>'
)
_NATIVE = (
    '<hierarchy rotation="0">'
    '<node class="android.widget.Button" resource-id="id/ok" text="OK" content-desc="" '
    'clickable="true" bounds="[0,0][100,50]"/></hierarchy>'
)


def test_webview_marker_sets_toolkit():
    assert parse_screen(_WEB).toolkit == "webview"
    assert parse_screen(_NATIVE).toolkit == "native"


def test_web_screen_case_wrapped_in_context_switch():
    web = parse_screen(_WEB)
    model = build_test_model(CrawlResult(screens={web.fingerprint: web}, transitions=[]), "com.app")
    case = model.cases[0]
    web_i = next(i for i, s in enumerate(case.steps) if s.action == ActionType.SWITCH_CONTEXT and s.text == "web")
    nat_i = next(i for i, s in enumerate(case.steps) if s.action == ActionType.SWITCH_CONTEXT and s.text == "native")
    asserts = [i for i, s in enumerate(case.steps) if s.action == ActionType.ASSERT]
    # web switch before the first assertion, native switch after the last.
    assert web_i < min(asserts) <= max(asserts) < nat_i


def test_native_screen_not_wrapped():
    nat = parse_screen(_NATIVE)
    model = build_test_model(CrawlResult(screens={nat.fingerprint: nat}, transitions=[]), "com.app")
    assert all(s.action != ActionType.SWITCH_CONTEXT for c in model.cases for s in c.steps)


def test_python_emitter_renders_the_switch():
    web = parse_screen(_WEB)
    model = build_test_model(CrawlResult(screens={web.fingerprint: web}, transitions=[]), "com.app")
    files = get_emitter("python_pytest").emit(model)
    code = "\n".join(files.values())
    assert "switch_to.context(" in code  # the generated test really switches context
    assert 'switch_to.context("NATIVE_APP")' in code
