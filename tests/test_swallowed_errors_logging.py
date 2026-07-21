"""A file the security scanners can't read/parse used to vanish from the results
with no trace. They now degrade the same way (empty findings, never raise) but
log the skip at debug, so a silent coverage gap is at least diagnosable.

These pin that logging so the diagnostics don't quietly regress to `pass`."""

import logging

import pytest

from framework.security.sast.android_manifest import AndroidManifestAnalyzer
from framework.security.sast.control_flow import ControlFlowAnalyzer
from framework.security.sast.crypto import CryptoAnalyzer
from framework.security.sast.insecure_api import InsecureAPIAnalyzer
from framework.security.sast.ios_plist import IOSPlistAnalyzer
from framework.security.supplychain.parsers import (
    CocoaPodsDependencyParser,
    GradleDependencyParser,
    JavaScriptDependencyParser,
    PythonDependencyParser,
)


@pytest.mark.parametrize(
    "call,logger_name",
    [
        (lambda p: CryptoAnalyzer().analyze(p), "framework.security.sast.crypto"),
        (lambda p: InsecureAPIAnalyzer().analyze(p), "framework.security.sast.insecure_api"),
        (lambda p: ControlFlowAnalyzer().analyze_python(p), "framework.security.sast.control_flow"),
        (lambda p: AndroidManifestAnalyzer().analyze(p), "framework.security.sast.android_manifest"),
        (lambda p: IOSPlistAnalyzer().analyze(p), "framework.security.sast.ios_plist"),
    ],
)
def test_sast_scanner_logs_and_survives_an_unreadable_file(call, logger_name, tmp_path, caplog):
    missing = tmp_path / "does_not_exist"
    with caplog.at_level(logging.DEBUG, logger=logger_name):
        findings = call(missing)
    assert findings == []  # degrades to no findings, never raises
    assert any(record.name == logger_name for record in caplog.records)  # skip logged


@pytest.mark.parametrize(
    "call,logger_name",
    [
        (lambda p: PythonDependencyParser().parse_requirements(p), "framework.security.supplychain.parsers"),
        (lambda p: JavaScriptDependencyParser().parse_package_json(p), "framework.security.supplychain.parsers"),
        (lambda p: GradleDependencyParser().parse_build_gradle(p), "framework.security.supplychain.parsers"),
        (lambda p: CocoaPodsDependencyParser().parse_podfile_lock(p), "framework.security.supplychain.parsers"),
    ],
)
def test_supplychain_parser_logs_and_survives_an_unreadable_file(call, logger_name, tmp_path, caplog):
    missing = tmp_path / "does_not_exist"
    with caplog.at_level(logging.DEBUG, logger=logger_name):
        deps = call(missing)
    assert deps == []  # no deps parsed, never raises
    assert any(record.name == logger_name for record in caplog.records)  # skip logged


def test_dashboard_db_destructor_logs_cleanup_error(caplog):
    from framework.dashboard import database as db_module

    class _BoomDB(db_module.DashboardDB):
        def __init__(self):  # skip real DB init; we only exercise __del__
            pass

        def close(self):
            raise RuntimeError("connection already gone")

    with caplog.at_level(logging.DEBUG, logger="framework.dashboard.database"):
        _BoomDB().__del__()  # must not raise, and must leave a trace
    assert any("cleanup" in record.message.lower() for record in caplog.records)
