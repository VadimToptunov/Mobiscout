"""Command-level tests for ``mobiscout crawl``.

The crawl command is a thin parse -> call -> print shell over the service layer,
so these drive it through ``CliRunner`` with the whole pipeline (driver build,
foreground check, crawl, kit write) stubbed to fakes — no device, no Appium, no
real subprocess. The focus is the opt-in ``--uninstall-after`` wiring: it must
invoke the right platform command, tolerate an uninstall failure, and stay off by
default.
"""

from click.testing import CliRunner

from framework.cli.crawl_commands import crawl
from framework.cli.crawl_service import ForegroundCheck, KitReport

_PKG = "com.example.app"


class _Result:
    screens = [object(), object()]
    transitions = [object()]


def _stub_pipeline(monkeypatch, uninstall_runs):
    """Replace the real crawl pipeline with fakes and capture uninstall subprocess calls."""
    monkeypatch.setattr("framework.crawler.classify.ensure_model", lambda: object())
    monkeypatch.setattr("framework.cli.crawl_service.build_crawl_driver", lambda **k: (object(), None))
    monkeypatch.setattr(
        "framework.cli.crawl_service.ensure_foreground",
        lambda *a, **k: ForegroundCheck(ok=True, current=_PKG, found=_PKG),
    )

    class _Crawler:
        def __init__(self, *a, **k):
            pass

        def crawl(self):
            return _Result()

    monkeypatch.setattr("framework.crawler.AppCrawler", _Crawler)
    monkeypatch.setattr("framework.cli.crawl_service.write_kit", lambda **k: KitReport())

    class _P:
        returncode = 0
        stdout = "Success\n"
        stderr = ""

    def _run(cmd, **kwargs):
        uninstall_runs.append(cmd)
        return _P()

    monkeypatch.setattr("framework.cli.crawl_service.subprocess.run", _run)


def test_crawl_uninstall_after_android_invokes_adb(monkeypatch, tmp_path):
    runs: list = []
    _stub_pipeline(monkeypatch, runs)
    result = CliRunner().invoke(
        crawl,
        ["--package", _PKG, "--serial", "ABC123", "--uninstall-after", "--output", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert runs == [["adb", "-s", "ABC123", "uninstall", _PKG]]


def test_crawl_uninstall_after_ios_invokes_simctl(monkeypatch, tmp_path):
    runs: list = []
    _stub_pipeline(monkeypatch, runs)
    result = CliRunner().invoke(
        crawl,
        [
            "--platform",
            "ios",
            "--package",
            "com.apple.Preferences",
            "--udid",
            "UDID-1",
            "--uninstall-after",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert runs == [["xcrun", "simctl", "uninstall", "UDID-1", "com.apple.Preferences"]]


def test_crawl_uninstall_failure_does_not_fail_the_crawl(monkeypatch, tmp_path):
    runs: list = []
    _stub_pipeline(monkeypatch, runs)

    def _boom(cmd, **kwargs):
        runs.append(cmd)
        raise OSError("adb not found")

    monkeypatch.setattr("framework.cli.crawl_service.subprocess.run", _boom)
    result = CliRunner().invoke(
        crawl,
        ["--package", _PKG, "--uninstall-after", "--output", str(tmp_path)],
    )
    # The uninstall was attempted but its failure is a warning only — crawl still succeeds.
    assert result.exit_code == 0, result.output
    assert runs == [["adb", "uninstall", _PKG]]


def test_crawl_without_uninstall_after_removes_nothing(monkeypatch, tmp_path):
    runs: list = []
    _stub_pipeline(monkeypatch, runs)
    result = CliRunner().invoke(crawl, ["--package", _PKG, "--output", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert runs == []  # default off — no uninstall command invoked
