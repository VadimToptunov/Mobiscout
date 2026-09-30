"""The JVM and .NET kits EXECUTED, not just compiled: each runs its real test runner (Maven,
Gradle, dotnet) against a device-free Appium server (tests/support/fake_appium_server.py) that
serves the same fake app the Python and JS kits run against — green on a healthy app, red when
a tap goes nowhere, on both platforms. Their clients talk to Appium over HTTP, so an in-process
fake (as for Python/JS) is not an option; a protocol-level fake is.

Needs Maven / Gradle / the .NET 10 SDK and network access, so it runs where
``MOBISCOUT_REAL_COMPILE=1`` (the CI codegen job); ``DOTNET`` may point at an SDK off PATH."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from framework.crawler.page_kit import build_target_framework
from framework.crawler.to_codegen import build_test_model
from tests.codegen.test_kit_execution import _fake_app, _ios_login_catalog, _shared_chrome

sys.path.insert(0, str(Path(__file__).parent.parent / "support"))
from fake_appium_server import FakeAppiumServer  # noqa: E402

# target -> (tool, arguments). Gradle's cleanTest: a changed server URL does not invalidate
# its up-to-date check, so without it the second run would report the first run's result.
_RUNNERS = {
    "java_testng": ("mvn", ["-q", "-B", "test"]),
    "java_cucumber": ("mvn", ["-q", "-B", "test"]),
    "kotlin_appium": ("gradle", ["--no-daemon", "--console=plain", "cleanTest", "test"]),
    "kotlin_cucumber": ("gradle", ["--no-daemon", "--console=plain", "cleanTest", "test"]),
    "csharp_nunit": ("dotnet", ["test", "-nologo"]),
    "csharp_reqnroll": ("dotnet", ["test", "-nologo"]),
}

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOBISCOUT_REAL_COMPILE"), reason="needs Maven/Gradle/.NET + network"
)


@pytest.fixture(autouse=True)
def _heuristic_only(monkeypatch):
    monkeypatch.setenv("MOBISCOUT_ML_AUTOTRAIN", "0")
    monkeypatch.setenv("MOBISCOUT_ML_MODEL", "/nonexistent.pkl")


def _tool(name):
    return (os.environ.get("DOTNET") if name == "dotnet" else None) or shutil.which(name)


def _run(kit: Path, tool: str, args, server: FakeAppiumServer) -> subprocess.CompletedProcess:
    return subprocess.run(
        [tool, *args],
        cwd=kit,
        capture_output=True,
        text=True,
        timeout=900,
        env={**os.environ, "MOBISCOUT_APPIUM_SERVER": server.url},
    )


@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("target", sorted(_RUNNERS))
def test_kit_runs_green_on_a_healthy_app_and_red_when_a_tap_goes_nowhere(target, platform, tmp_path):
    name, args = _RUNNERS[target]
    tool = _tool(name)
    if tool is None:
        pytest.skip(f"{name} not installed")
    ios = platform == "ios"
    result = _ios_login_catalog() if ios else _shared_chrome()
    package = "" if ios else "com.x"
    model = build_test_model(result, app_package="com.x", app_activity=None if ios else ".Main")
    for rel, content in (build_target_framework(target, result, model, "com.x") or {}).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    with FakeAppiumServer(_fake_app(result, package)) as server:
        healthy = _run(tmp_path, tool, args, server)
        assert not server.unknown, f"the kit called endpoints the fake does not serve: {server.unknown}"
    assert (
        healthy.returncode == 0
    ), f"{target} failed on a healthy app:\n{healthy.stdout[-5000:]}\n{healthy.stderr[-2000:]}"

    broken = _fake_app(result, package)
    broken["transitions"] = []
    with FakeAppiumServer(broken) as server:
        proc = _run(tmp_path, tool, args, server)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, f"{target} passed with navigation broken:\n{out[-5000:]}"
    assert "atalog" in out, f"the failure should be arriving on the Catalog screen:\n{out[-5000:]}"
