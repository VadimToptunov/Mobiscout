"""Service layer for ``mobiscout crawl``.

The orchestration — opening a crawler driver, getting the app to the foreground,
and writing the kit artifacts — lives here as plain functions so it is unit
-testable without a terminal (no ``click`` printing, no ``click.Abort``). The
command in :mod:`framework.cli.crawl_commands` stays a thin parse → call → print
shell: it turns these results into rich output and exit codes.

Failures a user needs to see are raised as :class:`CrawlServiceError` with a
ready-to-print message; the command catches it and aborts.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

from framework.domain import MobiscoutError
from framework.utils.logger import get_logger

logger = get_logger(__name__)


class CrawlServiceError(MobiscoutError):
    """A user-facing failure while setting up or running a crawl.

    The message is already phrased for the tester (it names the likely cause and
    the fix); the command prints it verbatim and aborts.
    """


def preflight_or_raise(platform: str, driver: str, server: str) -> List[str]:
    """Run the environment preflight *before* opening a session and fail fast.

    The Appium path (iOS, or Android over the ``appium`` driver) needs a server and
    an SDK; a missing one otherwise surfaces only as an opaque session timeout deep
    inside the driver. Running :func:`framework.health.preflight.preflight` up front
    turns that into an immediate, actionable error.

    Args:
        platform: ``"android"`` or ``"ios"``.
        driver: Android UI backend — ``"adb"`` or ``"appium"``.
        server: Appium server URL to probe.

    Returns:
        The warn-level check details (non-fatal) for the caller to log.

    Raises:
        CrawlServiceError: If any check is a hard failure, with the combined
            actionable messages (name, detail, and fix per failed check).
    """
    from framework.health.preflight import preflight

    results = preflight(platform, driver, server)
    failures = [r for r in results if r.level == "fail"]
    if failures:
        lines = []
        for r in failures:
            line = f"{r.name}: {r.detail}"
            if r.fix:
                line += f"\n    Fix: {r.fix}"
            lines.append("  - " + line)
        raise CrawlServiceError("Preflight failed before opening a session:\n" + "\n".join(lines))
    return [r.detail + (f" (fix: {r.fix})" if r.fix else "") for r in results if r.level == "warn"]


def uninstall_app(*, platform: str, package: str, serial: Optional[str], udid: Optional[str]) -> Tuple[bool, str]:
    """Remove the app under test from the device after a crawl (opt-in cleanup).

    Uses ``adb -s <serial> uninstall <pkg>`` for Android and
    ``xcrun simctl uninstall <udid> <bundleid>`` for iOS. Never raises for an
    uninstall failure — the caller logs the message as a warning; a failed cleanup
    must not fail the crawl.

    Args:
        platform: ``"android"`` or ``"ios"``.
        package: Android package or iOS bundle id to remove.
        serial: adb device serial (Android); omitted from the command when None.
        udid: Simulator/device UDID (iOS); defaults to ``booted`` when None.

    Returns:
        ``(ok, message)`` — ``ok`` True on a clean removal, else a phrased reason.
    """
    if platform == "ios":
        cmd = ["xcrun", "simctl", "uninstall", udid or "booted", package]
    else:
        cmd = ["adb"]
        if serial:
            cmd += ["-s", serial]
        cmd += ["uninstall", package]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"Could not uninstall {package}: {e}"
    # adb prints "Failure ..." to stdout while still exiting 0, so check both.
    if proc.returncode == 0 and "Failure" not in (proc.stdout or ""):
        return True, f"Uninstalled {package} from the device."
    detail = (proc.stderr or "").strip() or (proc.stdout or "").strip() or f"exit code {proc.returncode}"
    return False, f"Could not uninstall {package}: {detail}"


@dataclass
class ForegroundCheck:
    """Outcome of trying to get the app under test to the foreground.

    Attributes:
        ok: True if the app is now the foreground package.
        current: The foreground package actually observed (last read).
        found: The foreground package seen *before* any launch attempt.
        launched: True if we invoked the driver's ``launch`` to get it there.
        hint: A copy-pasteable manual-launch command, set only when ``ok`` is False.
    """

    ok: bool
    current: str
    found: str
    launched: bool = False
    hint: str = ""


@dataclass
class KitReport:
    """What :func:`write_kit` produced, for the command to narrate.

    Attributes:
        info: Ordered human-readable lines about artifacts written.
        warnings: Non-fatal problems (e.g. an unknown codegen target skipped).
        no_tests: True if there were no locatable elements, so no tests were emitted.
    """

    info: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    no_tests: bool = False


def build_crawl_driver(
    *,
    package: str,
    platform: str,
    driver: str,
    serial: Optional[str],
    udid: Optional[str],
    device_name: Optional[str],
    server: str,
    extra_caps: dict,
    launch_args: Tuple[str, ...],
    app_activity: Optional[str],
) -> Tuple[Any, Optional[Any]]:
    """Open the crawler driver for the requested platform/backend.

    Args:
        package: Android package or iOS bundle id under test.
        platform: ``"android"`` or ``"ios"``.
        driver: Android UI backend — ``"adb"`` (no server) or ``"appium"``.
        serial: adb device serial (Android/adb path).
        udid: Device/simulator UDID for an Appium session.
        device_name: Device name for the Appium session (defaulted per platform).
        server: Appium server URL.
        extra_caps: Extra Appium capabilities (KEY=VALUE already parsed).
        launch_args: iOS launch arguments passed to the app on start.
        app_activity: Android entry activity (Appium path).

    Returns:
        A ``(crawl_driver, appium_session)`` pair. ``appium_session`` is the same
        object when an Appium-owned session must be ``quit()`` at the end, else None.

    Raises:
        CrawlServiceError: If an Appium session could not be opened.
    """
    from framework.crawler import AdbCrawlerDriver, AndroidAppiumDriver, IOSCrawlerDriver

    # Fail-fast: when the chosen path needs a server (iOS, or Android over Appium),
    # run the environment preflight FIRST so a missing SDK/server/driver is reported
    # immediately instead of as an opaque session timeout. The adb path skips this.
    if platform == "ios" or driver == "appium":
        for warning in preflight_or_raise(platform, driver, server):
            logger.warning("Preflight warning: %s", warning)

    if platform == "ios":
        try:
            crawl_driver: Any = IOSCrawlerDriver(
                bundle_id=package,
                udid=udid,
                device_name=device_name or "iPhone 17",
                server=server,
                process_args=list(launch_args) or None,
            )
        except Exception as e:
            raise CrawlServiceError(
                f"Could not open an Appium iOS session ({e}). Is the Appium server running at {server}?"
            )
        return crawl_driver, crawl_driver

    if driver == "appium":
        from framework.health.preflight import ensure_android_home, resolve_android_home

        # Self-heal *our* env so the adb subprocesses spawned during the session
        # inherit ANDROID_HOME. This cannot fix a separately launched Appium server.
        ensure_android_home()
        try:
            crawl_driver = AndroidAppiumDriver(
                app_package=package,
                app_activity=app_activity,
                udid=udid,
                device_name=device_name or "Android Device",
                server=server,
                extra_caps=extra_caps,
            )
        except Exception as e:
            # The classic dead-end: the running Appium server has no ANDROID_HOME,
            # so UiAutomator2 fails deep with an opaque error. Detect the SDK here
            # and tell the tester exactly how to relaunch the server.
            text = str(e)
            if "ANDROID_HOME" in text or "ANDROID_SDK_ROOT" in text:
                detected = resolve_android_home()
                if detected:
                    raise CrawlServiceError(
                        f"The Appium server has no ANDROID_HOME. Detected an Android SDK at "
                        f"{detected}. Restart Appium with ANDROID_HOME={detected} "
                        f"(e.g. `ANDROID_HOME={detected} appium`)."
                    )
                raise CrawlServiceError(
                    "The Appium server has no ANDROID_HOME and no Android SDK was found on "
                    "this machine. Install the Android SDK and restart Appium with "
                    "ANDROID_HOME set to its path (e.g. `ANDROID_HOME=/path/to/sdk appium`)."
                )
            raise CrawlServiceError(
                f"Could not open an Appium Android session ({e}). Is the Appium server running at {server}?"
            )
        return crawl_driver, crawl_driver

    return AdbCrawlerDriver(serial=serial, launch_args=list(launch_args) or None), None


def ensure_foreground(crawl_driver: Any, package: str, platform: str) -> ForegroundCheck:
    """Make sure the app under test is the foreground app, launching it if we can.

    A capricious device often has the app not-yet-foreground (slow launch, splash,
    a stuck prior app). If the driver exposes ``launch`` we try it ourselves and
    re-check, so the crawl doesn't need a manual pre-launch every run.

    Args:
        crawl_driver: The driver to query/launch through.
        package: The package/bundle id that should be in the foreground.
        platform: ``"android"`` or ``"ios"`` — selects the manual-launch hint.

    Returns:
        A :class:`ForegroundCheck` describing what happened; ``ok`` False means the
        app never came forward and ``hint`` holds a manual command to try.
    """
    found = crawl_driver.current_package()
    if found == package:
        return ForegroundCheck(ok=True, current=found, found=found)

    launched = False
    launch = getattr(crawl_driver, "launch", None)
    current = found
    if callable(launch):
        launch(package)
        launched = True
        current = crawl_driver.current_package()

    if current == package:
        return ForegroundCheck(ok=True, current=current, found=found, launched=launched)

    hint = (
        f"adb shell monkey -p {package} -c android.intent.category.LAUNCHER 1"
        if platform == "android"
        else f"xcrun simctl launch booted {package}"
    )
    return ForegroundCheck(ok=False, current=current, found=found, launched=launched, hint=hint)


def write_kit(
    *,
    result: Any,
    output: str,
    package: str,
    targets: str,
    style: str,
    scaffold: bool,
    server: str,
    app_activity: Optional[str],
    launch_args: Tuple[str, ...],
    assert_values: bool = False,
) -> KitReport:
    """Write every artifact of a crawl kit to ``output`` and report what was written.

    Produces, under ``output``: the element inventory (Markdown + JSON), the
    interaction graph (Mermaid + DOT + JSON), the generated tests for each
    requested codegen target (flat files, or a Page-Object framework layout when
    ``style == "pom"``), and — if ``scaffold`` — a runnable project shell.

    Args:
        result: The :class:`CrawlResult` from the crawl.
        output: Destination directory (created if missing).
        package: App package/bundle id (labels the inventory and test setup).
        targets: Comma-separated codegen target ids.
        style: ``"flat"`` (standalone files) or ``"pom"`` (Page-Object framework).
        scaffold: Also write a runnable project shell around the tests.
        server: Appium server URL baked into a scaffolded project's config.
        app_activity: Android entry activity for the generated test setup.
        launch_args: iOS launch arguments recorded into the generated test setup.
        assert_values: Also pin observed static text values (TEXT_EQUALS) in the
            generated state tests. Opt-in; off keeps output VISIBLE-only.

    Returns:
        A :class:`KitReport` with info lines, non-fatal warnings, and whether tests
        were skipped for lack of locatable elements.
    """
    from framework.codegen import available_targets, get_emitter
    from framework.crawler import build_test_model
    from framework.crawler.graph import build_graph, to_dot, to_json, to_mermaid
    from framework.crawler.report import inventory_json_str, inventory_markdown
    from framework.licensing import allow_targets

    report = KitReport()
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)

    # Build the interaction graph once and thread it through inventory, the graph
    # writers, and the test model (which would otherwise rebuild it several times).
    # Deterministic for a given result, so every artifact is byte-identical.
    graph = build_graph(result, package)

    # 1) Element inventory (Markdown + JSON) — the tester-facing map.
    (out / "inventory.md").write_text(inventory_markdown(result, package, graph=graph), encoding="utf-8", newline="\n")
    (out / "inventory.json").write_text(inventory_json_str(result, package), encoding="utf-8", newline="\n")
    report.info.append(f"Inventory: {out / 'inventory.md'}")

    # 2) Interaction graph — Mermaid (renders on GitHub), Graphviz DOT, JSON.
    (out / "graph.mmd").write_text(to_mermaid(graph), encoding="utf-8", newline="\n")
    (out / "graph.dot").write_text(to_dot(graph), encoding="utf-8", newline="\n")
    (out / "graph.json").write_text(to_json(graph), encoding="utf-8", newline="\n")
    gm = graph.metrics()
    report.info.append(
        f"Graph: {gm['screens']} screens, {gm['transitions']} transitions, {gm['dead_ends']} dead-end(s)"
    )

    # 3) Tests. flat = one standalone file per target; pom = a framework layout
    # (Page Objects + conftest + POM-style tests) for the Python targets.
    target_ids = {t.id for t in available_targets()}
    model = build_test_model(
        result,
        app_package=package,
        app_activity=app_activity,
        launch_args=list(launch_args) or None,
        graph=graph,
        assert_values=assert_values,
    )
    if not model.cases:
        report.no_tests = True
        report.info.append("No locatable elements — no tests generated (see inventory.md).")

    # No-op on the open-core (unlimited) tier; a paid layer can cap the languages.
    requested = allow_targets([t.strip() for t in targets.split(",") if t.strip()])

    if style == "pom" and model.cases:
        from framework.crawler.page_kit import build_framework_kit

        framework_files = build_framework_kit(result, model, package)
        for rel, content in framework_files.items():
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")
        if framework_files:
            report.info.append(f"Framework (Page Objects + conftest + tests): {out}")

    for target in requested:
        if target not in target_ids:
            report.warnings.append(f"Unknown target '{target}'. Available: {', '.join(sorted(target_ids))}")
            continue
        # In pom mode the Python framework layout above already covers pytest.
        if style == "pom" and target == "python_pytest":
            continue
        for name, content in get_emitter(target).emit(model).items():
            dest = out / target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")
        report.info.append(f"Tests ({target}): {out / target}")

    # 4) Optional: a runnable project shell (deps + runner config + README) so the
    # output is `install && test` away from running — a new framework in place.
    if scaffold and model.cases:
        from framework.codegen.scaffold import scaffold_files

        wrote = False
        for target in requested:
            files = scaffold_files(model, target, server=server)
            if not files:
                continue
            for rel, content in files.items():
                (out / rel).write_text(content, encoding="utf-8", newline="\n")
            report.info.append(f"Scaffolded a runnable {target} project in {out} (see README.md)")
            wrote = True
            break  # one project shell per output dir
        if not wrote:
            report.warnings.append(
                f"No project scaffold for {', '.join(requested)} yet (specs written; add to your framework)."
            )

    return report
