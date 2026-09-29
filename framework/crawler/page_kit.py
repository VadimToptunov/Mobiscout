"""
Framework-structured output from a crawl — a Page-Object test framework, not one flat
smoke file.

Real teams keep locators inside page objects, the driver in a shared fixture, and tests
that read like intent. The crawl is first turned into the language-agnostic framework
model (:mod:`framework.codegen.framework_model`) — pages with intention methods and a
distinctive identity, scenarios as page calls — and then rendered per language. Python
(pytest + Appium) is rendered here::

    conftest.py              one Appium session per run + a cold app restart per test
    pages/base_page.py       locating / waiting / acting / settling, written once
    pages/<screen>_page.py   private locators + intention methods per screen
    tests/test_<screen>.py   scenarios about that screen
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from framework.codegen.framework_bdd_python import render_behave, render_pytest_bdd
from framework.codegen.framework_java import render_java
from framework.codegen.framework_js import render_js
from framework.codegen.framework_kotlin import render_kotlin
from framework.codegen.framework_model import FrameworkModel, build_framework_model
from framework.codegen.framework_python import render_python
from framework.codegen.ir import TestModel
from framework.crawler.app_crawler import CrawlResult

# Non-Python targets with a Page-Object framework renderer. Each renders a self-contained,
# runnable project (its own build file) into the kit's ``<target>/`` directory. A target
# without one still gets the flat emitter.
_TARGET_FRAMEWORKS: Dict[str, Callable[[FrameworkModel], Dict[str, str]]] = {
    "java_testng": render_java,
    "js_webdriverio": render_js,
    "kotlin_appium": render_kotlin,
    "python_pytest": render_python,
    "python_pytest_bdd": render_pytest_bdd,
}

# Targets that exist ONLY as a Page-Object framework: they are generated from a crawl (the
# page structure comes from its screens), in either style, and have no flat emitter.
FRAMEWORK_ONLY_TARGETS: Dict[str, Callable[[FrameworkModel], Dict[str, str]]] = {
    "python_behave": render_behave,
}


def build_framework_kit(result: CrawlResult, model: TestModel, app_package: str) -> Dict[str, str]:
    """A pytest Page-Object framework layout from a crawl (relative_path -> content)."""
    return render_python(build_framework_model(result, model, app_package))


def build_target_framework(
    target: str, result: CrawlResult, model: TestModel, app_package: str
) -> Optional[Dict[str, str]]:
    """The Page-Object framework for ``target`` (paths relative to ``<kit>/<target>/``), or
    ``None`` when the target has no framework renderer yet and should get the flat emitter."""
    render = _TARGET_FRAMEWORKS.get(target) or FRAMEWORK_ONLY_TARGETS.get(target)
    if render is None:
        return None
    return render(build_framework_model(result, model, app_package))
