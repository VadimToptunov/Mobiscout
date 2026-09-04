"""A JVM source file whose on-disk path doesn't match its `package` declaration won't
compile. The flat kit writes each emitted file at <out>/<target>/<path>, so an emitter
that returns `CrawlFlow.java` while the file says `package generated;` produces a kit
that javac/kotlinc reject in place (reported from dogfooding: tests were written but not
runnable where they landed). This pins that every JVM target's package == its path."""

import re

import pytest

from framework.codegen.ir import (
    ActionType,
    AssertionType,
    Platform,
    Selector,
    SelectorStrategy,
    Step,
    TestCase,
    TestModel,
)
from framework.codegen.targets import get_emitter

_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)", re.MULTILINE)


def _model() -> TestModel:
    sel = Selector(strategy=SelectorStrategy.ID, value="id/ok")
    return TestModel(
        name="Crawl Flow",
        app_package="com.example.app",
        platform=Platform.ANDROID,
        cases=[
            TestCase(
                name="home",
                description="home",
                steps=[
                    Step(ActionType.LAUNCH, description="Open app"),
                    Step(ActionType.ASSERT, selector=sel, assertion=AssertionType.VISIBLE, description="ok visible"),
                ],
            )
        ],
    )


@pytest.mark.parametrize("target", ["java_testng", "kotlin_appium", "kotlin_espresso", "java_cucumber"])
def test_jvm_source_path_matches_its_package(target):
    files = get_emitter(target).emit(_model())
    checked = 0
    for path, content in files.items():
        if not (path.endswith(".java") or path.endswith(".kt")):
            continue  # .feature (Gherkin) carries no package
        m = _PACKAGE_RE.search(content)
        assert m, f"{target}:{path} declares no package"
        pkg_dir = m.group(1).replace(".", "/")
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        assert parent == pkg_dir, (
            f"{target}: {path} declares `package {m.group(1)}` but sits at '{parent or '<root>'}' — "
            f"won't compile in place; emit it under '{pkg_dir}/'"
        )
        checked += 1
    assert checked > 0, f"{target} emitted no JVM source file to check"
