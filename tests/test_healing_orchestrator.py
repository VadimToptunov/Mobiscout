"""Tests for framework.healing.orchestrator.

These drive the end-to-end healing coordination against real collaborators (no
mocked internals): a SelectorFailure plus a real Appium-style page-source dump
is run through selector discovery -> ML-free matching -> Page Object rewrite, and
optionally a real git commit. The guarded behaviours: missing page source /
no alternatives / below-threshold confidence each fail with the right reason;
a healthy failure heals (dry-run reports success without touching the file, a
real run rewrites the Page Object); heal_all with auto_commit produces a real
Auto-heal commit and metadata; and the report summarises successes and failures.
"""

import subprocess
from pathlib import Path

import pytest

from framework.healing.failure_analyzer import FailureType, SelectorFailure
from framework.healing.orchestrator import HealingOrchestrator, HealingResult

PAGE_SOURCE_WITH_ID = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node class="android.widget.FrameLayout">
    <node class="android.widget.Button" resource-id="com.app:id/login"
          text="Login" clickable="true" content-desc="Login button"/>
  </node>
</hierarchy>
"""

PAGE_SOURCE_TEXT_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node class="android.widget.TextView" text="Hi"/>
</hierarchy>
"""

PAGE_SOURCE_NO_INTERACTIVE = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node class="android.view.View"/>
</hierarchy>
"""


def _run(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    _run(tmp_path, "init")
    _run(tmp_path, "config", "user.email", "healer@test.local")
    _run(tmp_path, "config", "user.name", "Healer")
    _run(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("seed\n")
    _run(tmp_path, "add", "README.md")
    _run(tmp_path, "commit", "-m", "initial")
    return tmp_path


def _failure(tmp_path, page_source: str = None, page_object: Path = None, name="test_login"):
    ps_path = None
    if page_source is not None:
        ps_path = tmp_path / f"{name}_source.xml"
        ps_path.write_text(page_source)
    return SelectorFailure(
        test_name=name,
        test_file=Path("tests/login_test.py"),
        selector_type="id",
        selector_value="old_login",
        failure_type=FailureType.SELECTOR_NOT_FOUND,
        error_message="Unable to find element",
        element_name="login_button",
        page_object_file=page_object,
        page_source_path=ps_path,
    )


def test_heal_failure_without_page_source(tmp_path):
    orch = HealingOrchestrator(tmp_path)
    result = orch.heal_failure(_failure(tmp_path, page_source=None))
    assert result.success is False
    assert result.error_message == "No page source available"
    assert result.alternatives_found == 0


def test_heal_failure_no_alternatives(tmp_path):
    orch = HealingOrchestrator(tmp_path)
    result = orch.heal_failure(_failure(tmp_path, page_source=PAGE_SOURCE_NO_INTERACTIVE))
    assert result.success is False
    assert result.error_message == "No alternative selectors found"
    assert result.alternatives_found == 0


def test_heal_failure_confidence_too_low(tmp_path):
    """A text-only element tops out at 0.70 combined; a 0.9 threshold rejects it
    but still surfaces the best_match that was considered."""
    orch = HealingOrchestrator(tmp_path, min_confidence=0.9)
    result = orch.heal_failure(_failure(tmp_path, page_source=PAGE_SOURCE_TEXT_ONLY))
    assert result.success is False
    assert "Confidence too low" in result.error_message
    assert result.best_match is not None
    assert result.best_match.combined_confidence < 0.9
    assert result.update_result is None


def test_heal_failure_dry_run_succeeds_without_writing(tmp_path):
    po = tmp_path / "login_page.py"
    po.write_text('login_button = ("id", "old_login")\n')
    before = po.read_text(encoding="utf-8")

    orch = HealingOrchestrator(tmp_path)
    result = orch.heal_failure(_failure(tmp_path, page_source=PAGE_SOURCE_WITH_ID, page_object=po), dry_run=True)

    assert result.success is True
    assert result.alternatives_found > 0
    # the ID selector wins and its value is the element's resource-id
    assert result.best_match.selector.selector_tuple == ("id", "com.app:id/login")
    assert result.update_result is None
    # dry run left the file untouched
    assert po.read_text(encoding="utf-8") == before


def test_heal_failure_real_run_rewrites_page_object(tmp_path):
    po = tmp_path / "login_page.py"
    po.write_text('login_button = ("id", "old_login")\n')

    orch = HealingOrchestrator(tmp_path)
    result = orch.heal_failure(_failure(tmp_path, page_source=PAGE_SOURCE_WITH_ID, page_object=po), dry_run=False)

    assert result.success is True
    assert result.update_result is not None and result.update_result.success is True
    content = po.read_text(encoding="utf-8")
    assert 'login_button = ("id", "com.app:id/login")' in content
    assert "# Auto-healed:" in content


def test_heal_all_with_auto_commit_creates_commit_and_metadata(repo):
    po = repo / "login_page.py"
    po.write_text('login_button = ("id", "old_login")\n')
    _run(repo, "add", "login_page.py")
    _run(repo, "commit", "-m", "add page object")

    orch = HealingOrchestrator(repo)
    failure = _failure(repo, page_source=PAGE_SOURCE_WITH_ID, page_object=po)

    results = orch.heal_all([failure], dry_run=False, auto_commit=True, branch_name="heal/login")

    assert len(results) == 1 and results[0].success is True
    # a real Auto-heal commit exists on the new branch
    log = subprocess.run(["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True, check=True).stdout
    assert "Auto-heal: Fixed broken selectors" in log
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert branch == "heal/login"
    # metadata sidecar written
    assert (repo / ".healing_metadata.json").exists()


def test_heal_all_dry_run_does_not_commit(repo):
    po = repo / "login_page.py"
    po.write_text('login_button = ("id", "old_login")\n')
    _run(repo, "add", "login_page.py")
    _run(repo, "commit", "-m", "add page object")

    orch = HealingOrchestrator(repo)
    failure = _failure(repo, page_source=PAGE_SOURCE_WITH_ID, page_object=po)

    results = orch.heal_all([failure], dry_run=True, auto_commit=True)

    assert results[0].success is True
    log = subprocess.run(["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True, check=True).stdout
    assert "Auto-heal" not in log


def test_analyze_failures_parses_and_enriches(tmp_path):
    junit = tmp_path / "results.xml"
    junit.write_text(
        '<testsuite name="s">'
        '<testcase name="test_login" classname="tests.login_test">'
        "<failure message=\"Unable to find element with Using='id', value='login_button'\">tb</failure>"
        "</testcase></testsuite>"
    )
    ps_dir = tmp_path / "src"
    ps_dir.mkdir()
    (ps_dir / "test_login_source.xml").write_text(PAGE_SOURCE_WITH_ID)
    po_dir = tmp_path / "pages"
    po_dir.mkdir()
    (po_dir / "login_page.py").write_text('login_button = ("id", "login_button")\n')

    orch = HealingOrchestrator(tmp_path)
    failures = orch.analyze_failures(junit, page_source_dir=ps_dir, page_objects_dir=po_dir)

    assert len(failures) == 1
    assert failures[0].selector_value == "login_button"
    assert failures[0].page_source_path == ps_dir / "test_login_source.xml"
    assert failures[0].page_object_file == po_dir / "login_page.py"


def test_generate_report_summarises_success_and_failure(tmp_path):
    orch = HealingOrchestrator(tmp_path)
    healed = orch.heal_failure(_failure(tmp_path, page_source=PAGE_SOURCE_WITH_ID, name="test_ok"), dry_run=True)
    failed = orch.heal_failure(_failure(tmp_path, page_source=None, name="test_bad"))

    report = orch.generate_report([healed, failed])

    assert "HEALING REPORT" in report
    assert "Total failures: 2" in report
    assert "Successfully healed: 1 (50.0%)" in report
    assert "Failed to heal: 1" in report
    assert "SUCCESSFUL HEALINGS:" in report
    assert "FAILED HEALINGS:" in report
    assert "No page source available" in report


def test_generate_report_no_results_no_zero_division(tmp_path):
    report = HealingOrchestrator(tmp_path).generate_report([])
    assert "Total failures: 0" in report
    assert "Successfully healed: 0 (0.0%)" in report


def test_healing_result_dataclass_defaults():
    r = HealingResult(
        failure=_failure(Path("."), page_source=None),
        alternatives_found=0,
        best_match=None,
        update_result=None,
        success=False,
    )
    assert r.error_message is None
