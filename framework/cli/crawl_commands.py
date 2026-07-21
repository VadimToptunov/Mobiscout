"""
`mobiscout crawl` — point at a running app, get a full test kit.

Autonomously crawls the app on a connected device (via adb), then writes the
artifacts a tester needs: a per-screen element inventory (Markdown + JSON), an
accessibility report, and runnable test code in the chosen language(s).
"""

from pathlib import Path

import click

from framework.cli.rich_output import print_error, print_header, print_info, print_success
from framework.utils.logger import get_logger

logger = get_logger(__name__)


@click.command()
@click.option("--package", required=True, help="App under test: Android package or iOS bundle id")
@click.option(
    "--platform",
    type=click.Choice(["android", "ios"]),
    default="android",
    show_default=True,
    help="android crawls over adb; ios crawls over an Appium/XCUITest session",
)
@click.option(
    "--driver",
    type=click.Choice(["adb", "appium"]),
    default="adb",
    show_default=True,
    help="Android UI backend: adb (no server) or an Appium/UiAutomator2 session (real devices, cloud)",
)
@click.option("--serial", default=None, help="adb device serial (Android/adb; default: the only connected device)")
@click.option("--udid", default=None, help="Device/simulator UDID for an Appium session")
@click.option("--device-name", default=None, help="Device name for the Appium session")
@click.option("--server", default="http://localhost:4723", show_default=True, help="Appium server URL")
@click.option("--cap", "caps", multiple=True, help="Extra Appium capability KEY=VALUE (repeatable; e.g. cloud grids)")
@click.option("--output", default="crawl-kit", help="Output directory for the artifacts")
@click.option("--targets", default="python_pytest", help="Comma-separated codegen targets for the tests")
@click.option("--app-activity", default=None, help="Android entry activity (for the generated test setup)")
@click.option(
    "--style",
    type=click.Choice(["flat", "pom"]),
    default="flat",
    show_default=True,
    help="flat = standalone test files; pom = a framework (Page Objects + conftest + tests). pom: python targets",
)
@click.option(
    "--scaffold",
    is_flag=True,
    help="Also write a runnable project shell (deps + runner config + README) around the tests",
)
@click.option("--max-steps", default=40, show_default=True, help="Crawl step budget")
@click.option("--max-depth", default=8, show_default=True, help="Crawl depth budget")
@click.option(
    "--launch-arg",
    "launch_args",
    multiple=True,
    help="iOS launch argument passed to the app on start (repeatable) — e.g. "
    "--launch-arg -MyAppStartUnlocked --launch-arg 1 to skip a login gate",
)
def crawl(
    package,
    platform,
    driver,
    serial,
    udid,
    device_name,
    server,
    caps,
    output,
    targets,
    app_activity,
    style,
    scaffold,
    max_steps,
    max_depth,
    launch_args,
):
    """
    Crawl a running app and export an element inventory + tests.

    Android over adb (default) or over an Appium/UiAutomator2 session
    (--driver appium, which unlocks real devices and cloud grids via --cap), and
    iOS over an Appium/XCUITest session.

    Examples:
        mobiscout crawl --package com.example.app --targets python_pytest,java_testng
        mobiscout crawl --package com.example.app --driver appium --udid <UDID>
        mobiscout crawl --platform ios --package com.apple.Preferences --udid <UDID>
    """
    from framework.cli.crawl_service import CrawlServiceError, build_crawl_driver, ensure_foreground, write_kit
    from framework.crawler import AppCrawler
    from framework.crawler.classify import ensure_model

    print_header("🕷️  Crawling app", f"{package} ({platform})")

    # Provision the element-classification model (trains from synthetic data in
    # ~1s on first run, then cached). Never fatal: falls back to the heuristic.
    if ensure_model() is None:
        print_info("Element typing: using the rule heuristic (ML model unavailable).")

    extra_caps = dict(c.split("=", 1) for c in caps if "=" in c)
    try:
        crawl_driver, appium_session = build_crawl_driver(
            package=package,
            platform=platform,
            driver=driver,
            serial=serial,
            udid=udid,
            device_name=device_name,
            server=server,
            extra_caps=extra_caps,
            launch_args=launch_args,
            app_activity=app_activity,
        )
    except CrawlServiceError as e:
        print_error(str(e))
        raise click.Abort()

    # Get the app to the foreground (launching it ourselves if the device left it
    # behind), so a capricious device doesn't need a manual pre-launch every time.
    check = ensure_foreground(crawl_driver, package, platform)
    if check.launched:
        print_info(f"App '{package}' was not in the foreground (found '{check.found}') — launched it.")
    if not check.ok:
        print_error(
            f"App '{package}' is not in the foreground (found '{check.current}'). Launch it first: {check.hint}"
        )
        if appium_session:
            appium_session.quit()
        raise click.Abort()

    try:
        result = AppCrawler(crawl_driver, package, max_steps=max_steps, max_depth=max_depth).crawl()
    finally:
        if appium_session:
            appium_session.quit()
    print_success(f"Discovered {len(result.screens)} screen(s), {len(result.transitions)} transition(s)")

    report = write_kit(
        result=result,
        output=output,
        package=package,
        targets=targets,
        style=style,
        scaffold=scaffold,
        server=server,
        app_activity=app_activity,
        launch_args=launch_args,
    )
    for line in report.info:
        print_info(line)
    for warning in report.warnings:
        print_error(warning)

    print_success(f"Kit written to {Path(output).absolute()}")
    logger.info(f"Crawl kit for {package}: {len(result.screens)} screens -> {output}")
