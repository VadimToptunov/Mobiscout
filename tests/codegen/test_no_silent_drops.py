"""Nothing the kit leaves out is left out silently: a scenario that cannot be built becomes a
skipped test that carries the reason (and a line in generation-report.md), and one target
failing to generate never costs the kit the others."""

import os

import pytest

from framework.codegen.bdd_model import build_bdd_model, render_feature
from framework.codegen.framework_model import build_framework_model
from framework.crawler.page_kit import build_target_framework
from framework.crawler.to_codegen import build_test_model
from tests.codegen.test_kit_execution import _emit_pom_kit, _fake_app, _run_pytest, _unlabelled_destination

_REASON = "Nothing on the"


def _model(result):
    return build_test_model(result, app_package="com.x", app_activity=".Main")


def test_an_unprovable_navigation_becomes_a_skipped_scenario_with_its_reason():
    result = _unlabelled_destination()
    fm = build_framework_model(result, _model(result), "com.x")
    assert fm.skipped, "the tap into an unlabelled screen cannot be proven — it must be reported, not dropped"
    assert all(sc.skip and _REASON in sc.skip for sc in fm.skipped), [sc.skip for sc in fm.skipped]
    assert not any(sc.skip for sc in fm.scenarios)


@pytest.mark.parametrize(
    "target, stub",
    [
        ("python_pytest", "@pytest.mark.skip(reason="),
        ("java_testng", "throw new SkipException("),
        ("kotlin_appium", "@Disabled("),
        ("js_webdriverio", "it.skip("),
        ("python_pytest_bdd", "# Not generated — needs attention:"),
        ("java_cucumber", "# Not generated — needs attention:"),
        ("js_cucumber", "# Not generated — needs attention:"),
        ("csharp_nunit", "[Test, Ignore("),
        ("csharp_reqnroll", "# Not generated — needs attention:"),
    ],
)
def test_every_target_shows_what_it_could_not_generate(target, stub):
    result = _unlabelled_destination()
    source = "\n".join((build_target_framework(target, result, _model(result), "com.x") or {}).values())
    assert stub in source and _REASON in source, f"{target} dropped the scenario silently"


def test_the_python_kit_reports_the_stub_as_skipped_with_its_reason(tmp_path):
    result = _unlabelled_destination()
    kit = _emit_pom_kit(result, tmp_path)
    proc = _run_pytest(kit, _fake_app(result, "com.x"), verbose=True)
    assert proc.returncode == 0, proc.stdout
    assert "SKIPPED" in proc.stdout, proc.stdout


def test_generation_report_lists_skipped_scenarios(tmp_path):
    from framework.crawler.pipeline import build_kit

    summary = build_kit(_unlabelled_destination(), {"package": "com.x", "output": str(tmp_path)})
    report = (tmp_path / "generation-report.md").read_text(encoding="utf-8")
    assert summary["not_generated"] >= 1 and "Not generated — needs attention" in report and _REASON in report


def test_one_target_failing_does_not_cost_the_kit_the_others(tmp_path, monkeypatch):
    from framework.crawler import page_kit
    from framework.crawler.pipeline import build_kit

    def broken(_fm):
        raise RuntimeError("renderer exploded")

    monkeypatch.setitem(page_kit._TARGET_FRAMEWORKS, "java_testng", broken)
    summary = build_kit(
        _unlabelled_destination(),
        {"package": "com.x", "output": str(tmp_path), "targets": ["java_testng", "python_pytest"]},
    )
    assert summary["targets"] == ["python_pytest"]
    assert "renderer exploded" in summary["errors"]["java_testng"]
    assert (tmp_path / "java_testng" / "GENERATION_ERROR.md").exists()
    assert (tmp_path / "python_pytest" / "conftest.py").exists()
    assert "java_testng" in (tmp_path / "generation-report.md").read_text(encoding="utf-8")


def test_a_bdd_feature_lists_what_it_is_missing():
    result = _unlabelled_destination()
    bm = build_bdd_model(build_framework_model(result, _model(result), "com.x"))
    text = "\n".join(render_feature(f, "com.x") for f in bm.features)
    assert "# Not generated — needs attention:" in text and _REASON in text, text


@pytest.mark.parametrize("flavour", ["pytest_bdd", "behave"])
def test_a_feature_holding_only_notes_runs_cleanly(tmp_path, flavour):
    pytest.importorskip("behave" if flavour == "behave" else "pytest_bdd")
    from tests.codegen.test_kit_execution import _emit_python_bdd_kit, _run_python_bdd

    result = _unlabelled_destination()
    kit = _emit_python_bdd_kit(result, tmp_path, flavour)
    assert any("# Not generated" in p.read_text(encoding="utf-8") for p in (kit / "features").glob("*.feature"))
    proc = _run_python_bdd(kit, _fake_app(result, "com.x"), flavour)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


@pytest.mark.skipif(not os.environ.get("MOBISCOUT_REAL_COMPILE"), reason="needs Maven/Gradle/.NET + network")
@pytest.mark.parametrize(
    "target, tool, args",
    [
        ("java_testng", "mvn", ["-q", "-B", "test-compile"]),
        ("kotlin_appium", "gradle", ["-q", "--no-daemon", "compileTestKotlin"]),
        ("csharp_nunit", "dotnet", ["build", "-nologo", "-warnaserror"]),
    ],
)
def test_skipped_stubs_compile(tmp_path, target, tool, args):
    import shutil
    import subprocess

    exe = (os.environ.get("DOTNET") if tool == "dotnet" else None) or shutil.which(tool)
    if exe is None:
        pytest.skip(f"{tool} not installed")
    result = _unlabelled_destination()
    for rel, content in (build_target_framework(target, result, _model(result), "com.x") or {}).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    proc = subprocess.run([exe, *args], cwd=tmp_path, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, f"{target} with skipped stubs does not compile:\n{proc.stdout}\n{proc.stderr}"
