"""Tests for framework.health.doctor.SystemDoctor.

Guards the individual health checks against real environment state (Python
version, importable packages, filesystem write access, config-file presence) and
the aggregation/reporting. Checks that shell out (git/appium) and device
discovery are asserted only on the shape of their HealthCheck result. A
regression test pins the pyyaml->yaml import-name fix so the package check can't
silently report PyYAML as missing again.
"""

import io

from rich.console import Console

from framework.health.doctor import CheckStatus, HealthCheck, SystemDoctor


def _doctor() -> SystemDoctor:
    return SystemDoctor(Console(file=io.StringIO()))


def test_python_check_passes_on_modern_python():
    check = _doctor()._check_python(verbose=False)
    assert check.status == CheckStatus.PASS
    assert "Python" in check.message


def test_packages_check_passes_with_installed_deps():
    """Regression: the required-package check must resolve pyyaml via its import
    name 'yaml'; with all deps installed the check passes and lists none missing."""
    check = _doctor()._check_packages(verbose=False)
    assert check.status == CheckStatus.PASS, check.message
    assert "pyyaml" not in check.message


def test_permissions_check_pass_in_writable_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    check = _doctor()._check_permissions(verbose=False)
    assert check.status == CheckStatus.PASS


def test_config_check_pass_when_files_present(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[tool]\n")
    (tmp_path / "requirements.txt").write_text("rich\n")
    monkeypatch.chdir(tmp_path)
    check = _doctor()._check_config(verbose=False)
    assert check.status == CheckStatus.PASS


def test_config_check_warns_when_some_missing(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[tool]\n")  # requirements.txt absent
    monkeypatch.chdir(tmp_path)
    check = _doctor()._check_config(verbose=False)
    assert check.status == CheckStatus.WARN
    assert "requirements.txt" in check.message


def test_config_check_fails_when_all_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    check = _doctor()._check_config(verbose=False)
    assert check.status == CheckStatus.FAIL


def test_git_check_returns_valid_status():
    check = _doctor()._check_git(verbose=False)
    assert isinstance(check, HealthCheck)
    assert check.status in {CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL}


def test_appium_check_returns_valid_status():
    check = _doctor()._check_appium(verbose=False)
    # appium is optional -> PASS if present else WARN, never a hard error object
    assert check.status in {CheckStatus.PASS, CheckStatus.WARN}


def test_run_all_checks_and_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool]\n")
    (tmp_path / "requirements.txt").write_text("rich\n")

    doctor = _doctor()
    checks = doctor.run_all_checks(verbose=False)
    assert len(checks) == 11  # + Native Core (V1)
    assert all(isinstance(c, HealthCheck) for c in checks)

    passed, failed, warned, skipped = doctor.generate_report()
    assert passed + failed + warned + skipped == len(checks)
    # the four counts partition the checks exactly
    assert passed == sum(1 for c in checks if c.status == CheckStatus.PASS)

    # print_report must render without raising and produce output
    doctor.print_report(verbose=False)
    assert doctor.console.file.getvalue()  # something was written


def test_android_sdk_check_passes_when_env_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    check = _doctor()._check_android_sdk(verbose=False)
    assert check.status == CheckStatus.PASS
    assert str(tmp_path) in check.message


def test_android_sdk_check_warns_when_detected_but_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr("framework.health.preflight.resolve_android_home", lambda: str(tmp_path))
    check = _doctor()._check_android_sdk(verbose=False)
    assert check.status == CheckStatus.WARN
    assert check.fix_command == f"export ANDROID_HOME={tmp_path}"


def test_android_sdk_check_fails_when_no_sdk(monkeypatch):
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr("framework.health.preflight.resolve_android_home", lambda: None)
    check = _doctor()._check_android_sdk(verbose=False)
    assert check.status == CheckStatus.FAIL
    assert check.fix_command


def test_appium_check_warns_when_a_driver_is_missing(monkeypatch):
    """When appium is present but a required driver is missing, warn with a fix."""
    import framework.health.doctor as doctor_mod

    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _: "/usr/local/bin/appium")

    class _Result:
        returncode = 0
        stdout = "2.11.0"

    monkeypatch.setattr(doctor_mod.subprocess, "run", lambda *a, **k: _Result())
    monkeypatch.setattr(
        "framework.health.preflight.installed_appium_drivers",
        lambda: {"uiautomator2": "2.34.1"},  # xcuitest missing
    )
    check = _doctor()._check_appium(verbose=False)
    assert check.status == CheckStatus.WARN
    assert "xcuitest" in check.message
    assert check.fix_command == "appium driver install xcuitest"


def test_driver_manager_check_warns_on_npm_11(monkeypatch):
    """npm >= 11 breaks Appium's in-place `driver update`: WARN (not FAIL), and
    the fix is the verified non-destructive reinstall — not a Node/npm downgrade,
    since installed drivers keep working and a fresh install is unaffected."""
    monkeypatch.setattr(
        "framework.health.preflight.node_npm_versions",
        lambda: ("v25.0.0", "11.0.0"),
    )
    check = _doctor()._check_driver_manager(verbose=False)
    assert check.status == CheckStatus.WARN
    assert "11.0.0" in check.message
    assert check.fix_command is not None
    assert "appium driver uninstall" in check.fix_command and "appium driver install" in check.fix_command
    # The old, destructive advice must be gone.
    assert "nvm install --lts" not in check.fix_command
    assert "npm <= 10" not in check.fix_command


def test_driver_manager_check_passes_on_npm_10(monkeypatch):
    monkeypatch.setattr(
        "framework.health.preflight.node_npm_versions",
        lambda: ("v20.11.0", "10.2.4"),
    )
    check = _doctor()._check_driver_manager(verbose=False)
    assert check.status == CheckStatus.PASS
    assert check.fix_command is None


def test_driver_manager_check_passes_when_node_absent(monkeypatch):
    """No node/npm on the machine: nothing to diagnose, so PASS (not a false WARN)."""
    monkeypatch.setattr(
        "framework.health.preflight.node_npm_versions",
        lambda: (None, None),
    )
    check = _doctor()._check_driver_manager(verbose=False)
    assert check.status == CheckStatus.PASS


def test_apply_fixes_self_heals_android_home_and_prints_persistent_line(monkeypatch):
    """--fix calls ensure_android_home and reports both the process heal and the
    exact export line to persist it across shells (never editing shell files)."""
    import framework.cli.doctor_command as dc

    monkeypatch.setattr("framework.health.preflight.ensure_android_home", lambda: "/opt/android/sdk")
    checks = [
        HealthCheck("Android SDK", CheckStatus.WARN, "detected but unset", "export ANDROID_HOME=/opt/android/sdk")
    ]
    lines = dc.apply_fixes(checks, Console(file=io.StringIO()))
    assert any("self-healed" in ln and "/opt/android/sdk" in ln for ln in lines)
    assert any("export ANDROID_HOME=/opt/android/sdk" in ln for ln in lines)


def test_apply_fixes_reports_when_android_home_cannot_be_healed(monkeypatch):
    import framework.cli.doctor_command as dc

    monkeypatch.setattr("framework.health.preflight.ensure_android_home", lambda: None)
    checks = [HealthCheck("Android SDK", CheckStatus.FAIL, "no sdk", "Install the Android SDK")]
    lines = dc.apply_fixes(checks, Console(file=io.StringIO()))
    assert any("Could not self-heal ANDROID_HOME" in ln for ln in lines)


def test_apply_fixes_attempts_driver_install_and_survives_failure(monkeypatch):
    """A missing-driver WARN triggers `appium driver install`; an npm failure is
    caught and reported, not raised."""
    import framework.cli.doctor_command as dc

    monkeypatch.setattr("framework.health.preflight.ensure_android_home", lambda: "/sdk")

    captured = {}

    def _run(cmd, **kwargs):
        captured["cmd"] = cmd
        raise OSError("npm exploded")

    monkeypatch.setattr(dc.subprocess, "run", _run)
    checks = [HealthCheck("Appium", CheckStatus.WARN, "missing xcuitest", "appium driver install xcuitest")]
    lines = dc.apply_fixes(checks, Console(file=io.StringIO()))
    assert captured["cmd"] == ["appium", "driver", "install", "xcuitest"]
    assert any("Failed" in ln or "Could not install" in ln for ln in lines)


def test_apply_fixes_reports_successful_driver_install(monkeypatch):
    import framework.cli.doctor_command as dc

    class _P:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(dc.subprocess, "run", lambda cmd, **k: _P())
    checks = [HealthCheck("Appium", CheckStatus.WARN, "missing xcuitest", "appium driver install xcuitest")]
    lines = dc.apply_fixes(checks, Console(file=io.StringIO()))
    assert any("Installed Appium driver 'xcuitest'" in ln for ln in lines)


def test_apply_fixes_only_acts_on_failed_or_warned_checks(monkeypatch):
    """Passing checks are left alone — a passing Android SDK triggers no heal."""
    import framework.cli.doctor_command as dc

    def _must_not_run():
        raise AssertionError("ensure_android_home must not run for a passing check")

    monkeypatch.setattr("framework.health.preflight.ensure_android_home", _must_not_run)
    checks = [HealthCheck("Android SDK", CheckStatus.PASS, "ANDROID_HOME=/sdk")]
    lines = dc.apply_fixes(checks, Console(file=io.StringIO()))
    assert lines == ["No safe automatic fixes to apply."]


def test_generate_report_counts_each_status():
    doctor = _doctor()
    doctor.checks = [
        HealthCheck("a", CheckStatus.PASS, "ok"),
        HealthCheck("b", CheckStatus.FAIL, "bad"),
        HealthCheck("c", CheckStatus.WARN, "meh"),
        HealthCheck("d", CheckStatus.SKIP, "skip"),
        HealthCheck("e", CheckStatus.PASS, "ok"),
    ]
    assert doctor.generate_report() == (2, 1, 1, 1)
