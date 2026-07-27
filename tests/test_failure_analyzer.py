"""Tests for framework.healing.failure_analyzer.

These guard detection of broken-selector test failures from JUnit XML and raw
pytest output, the extraction of the (selector_type, value) pair from error
text, the enrichment passes that link a failure to its screenshot / page-source
/ Page Object file, and the human-readable report. A passing test must never be
reported as a selector failure.
"""

from pathlib import Path

from framework.healing.failure_analyzer import (
    FailureAnalyzer,
    FailureType,
    SelectorFailure,
)

JUNIT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite" tests="2">
  <testcase name="test_login" classname="tests.login_test">
    <failure message="Unable to find element with Using='id', value='login_button'">Traceback...</failure>
  </testcase>
  <testcase name="test_home" classname="tests.home_test"/>
</testsuite>
"""

JUNIT_TESTSUITES = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="s1">
    <testcase name="test_cart" classname="tests.cart_test">
      <error message="NoSuchElementException: element with By.id: cart_icon not found">x</error>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_analyze_junit_detects_selector_failure(tmp_path):
    xml = tmp_path / "results.xml"
    xml.write_text(JUNIT_XML)

    failures = FailureAnalyzer().analyze_junit_results(xml)

    assert len(failures) == 1
    f = failures[0]
    assert f.test_name == "test_login"
    assert f.selector_type == "id"
    assert f.selector_value == "login_button"
    assert f.failure_type == FailureType.SELECTOR_NOT_FOUND
    # classname is mapped to a file path
    assert f.test_file == Path("tests/login_test.py")


def test_analyze_junit_testsuites_root(tmp_path):
    xml = tmp_path / "results.xml"
    xml.write_text(JUNIT_TESTSUITES)
    failures = FailureAnalyzer().analyze_junit_results(xml)
    assert len(failures) == 1
    assert failures[0].selector_value == "cart_icon"


def test_analyze_junit_ignores_passing_tests(tmp_path):
    xml = tmp_path / "pass.xml"
    xml.write_text('<testsuite name="s"><testcase name="test_ok" classname="tests.ok"/></testsuite>')
    assert FailureAnalyzer().analyze_junit_results(xml) == []


def test_analyze_junit_malformed_xml_returns_empty(tmp_path):
    xml = tmp_path / "bad.xml"
    xml.write_text("<not-closed>")
    assert FailureAnalyzer().analyze_junit_results(xml) == []


def test_analyze_test_results_missing_file_returns_empty(tmp_path):
    assert FailureAnalyzer().analyze_test_results(tmp_path / "nope.xml") == []


def test_analyze_test_results_dispatches_by_extension(tmp_path):
    xml = tmp_path / "r.xml"
    xml.write_text(JUNIT_XML)
    failures = FailureAnalyzer().analyze_test_results(xml)
    assert len(failures) == 1 and failures[0].selector_value == "login_button"


def test_analyze_pytest_output_text(tmp_path):
    output = "\n".join(
        [
            "module.py::test_login FAILED",
            "Unable to find element with Using='id', value='login_button'",
            "  at some traceback line",
            "module.py::test_next PASSED",
        ]
    )
    txt = tmp_path / "out.txt"
    txt.write_text(output)

    failures = FailureAnalyzer().analyze_test_results(txt)
    assert len(failures) == 1
    assert failures[0].selector_value == "login_button"
    assert "test_login" in failures[0].test_name


def test_enrichment_links_screenshot_page_source_and_page_object(tmp_path):
    xml = tmp_path / "results.xml"
    xml.write_text(JUNIT_XML)
    analyzer = FailureAnalyzer()
    analyzer.analyze_junit_results(xml)

    # screenshots
    shots = tmp_path / "shots"
    shots.mkdir()
    shot = shots / "failure_test_login_1.png"
    shot.write_bytes(b"png")
    analyzer.enrich_with_screenshots(shots)
    assert analyzer.failures[0].screenshot_path == shot

    # page source dumps
    src = tmp_path / "src"
    src.mkdir()
    dump = src / "test_login_source.xml"
    dump.write_text("<hierarchy/>")
    analyzer.enrich_with_page_source(src)
    assert analyzer.failures[0].page_source_path == dump
    assert analyzer.failures[0].page_source == "<hierarchy/>"

    # page object files
    po_dir = tmp_path / "pages"
    po_dir.mkdir()
    po = po_dir / "login_page.py"
    po.write_text('class LoginPage:\n    login_button = ("id", "login_button")\n')
    analyzer.enrich_with_page_objects(po_dir)
    assert analyzer.failures[0].page_object_file == po
    assert analyzer.failures[0].page_object_class == "LoginPage"


def test_generate_report_empty_and_populated(tmp_path):
    analyzer = FailureAnalyzer()
    assert analyzer.generate_report() == "No selector failures detected."

    xml = tmp_path / "results.xml"
    xml.write_text(JUNIT_XML)
    analyzer.analyze_junit_results(xml)
    report = analyzer.generate_report()
    assert "SELECTOR FAILURE ANALYSIS" in report
    assert "test_login" in report
    assert "login_button" in report


def test_selector_failure_properties():
    f = SelectorFailure(
        test_name="t",
        test_file=Path("t.py"),
        selector_type="id",
        selector_value="btn",
        failure_type=FailureType.SELECTOR_NOT_FOUND,
        error_message="boom",
        element_name="submit",
        page_object_class="P",
    )
    assert f.selector_tuple == ("id", "btn")
    assert f.selector == "id=btn"
    assert f.element_info["selector_value"] == "btn"
    assert f.element_info["element_name"] == "submit"
    # no page source path set -> None
    assert f.page_source is None
