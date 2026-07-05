"""
`observe crawl` — point at a running app, get a full test kit.

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
@click.option("--serial", default=None, help="adb device serial (Android; default: the only connected device)")
@click.option("--udid", default=None, help="iOS simulator/device UDID (booted device)")
@click.option("--device-name", default="iPhone 17", show_default=True, help="iOS device name for the Appium session")
@click.option("--server", default="http://localhost:4723", show_default=True, help="Appium server URL (iOS)")
@click.option("--output", default="crawl-kit", help="Output directory for the artifacts")
@click.option("--targets", default="python_pytest", help="Comma-separated codegen targets for the tests")
@click.option("--app-activity", default=None, help="Android entry activity (for the generated test setup)")
@click.option("--max-steps", default=40, show_default=True, help="Crawl step budget")
@click.option("--max-depth", default=8, show_default=True, help="Crawl depth budget")
def crawl(package, platform, serial, udid, device_name, server, output, targets, app_activity, max_steps, max_depth):
    """
    Crawl a running app and export an element inventory + tests.

    Android (over adb) or iOS (over an Appium/XCUITest session — requires a
    running Appium server and a booted simulator/device).

    Examples:
        observe crawl --package com.example.app --targets python_pytest,java_testng
        observe crawl --platform ios --package com.apple.Preferences --udid <UDID>
    """
    from framework.codegen import available_targets, get_emitter
    from framework.crawler import AdbCrawlerDriver, AppCrawler, IOSCrawlerDriver, build_test_model
    from framework.crawler.report import inventory_json_str, inventory_markdown

    print_header("🕷️  Crawling app", f"{package} ({platform})")

    ios_driver = None
    if platform == "ios":
        try:
            driver = IOSCrawlerDriver(bundle_id=package, udid=udid, device_name=device_name, server=server)
        except Exception as e:
            print_error(f"Could not open an Appium iOS session ({e}). Is the Appium server running at {server}?")
            raise click.Abort()
        ios_driver = driver
    else:
        driver = AdbCrawlerDriver(serial=serial)

    current = driver.current_package()
    if current != package:
        hint = (
            f"adb shell monkey -p {package} -c android.intent.category.LAUNCHER 1"
            if platform == "android"
            else f"xcrun simctl launch booted {package}"
        )
        print_error(f"App '{package}' is not in the foreground (found '{current}'). Launch it first: {hint}")
        if ios_driver:
            ios_driver.quit()
        raise click.Abort()

    try:
        result = AppCrawler(driver, package, max_steps=max_steps, max_depth=max_depth).crawl()
    finally:
        if ios_driver:
            ios_driver.quit()
    print_success(f"Discovered {len(result.screens)} screen(s), {len(result.transitions)} transition(s)")

    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)

    # 1) Element inventory (Markdown + JSON) — the tester-facing map.
    (out / "inventory.md").write_text(inventory_markdown(result, package), encoding="utf-8", newline="\n")
    (out / "inventory.json").write_text(inventory_json_str(result, package), encoding="utf-8", newline="\n")
    print_info(f"Inventory: {out / 'inventory.md'}")

    # 2) Tests in each requested language.
    target_ids = {t.id for t in available_targets()}
    model = build_test_model(result, app_package=package, app_activity=app_activity)
    if not model.cases:
        print_info("No locatable elements — no tests generated (see inventory.md).")
    for target in [t.strip() for t in targets.split(",") if t.strip()]:
        if target not in target_ids:
            print_error(f"Unknown target '{target}'. Available: {', '.join(sorted(target_ids))}")
            continue
        for name, content in get_emitter(target).emit(model).items():
            dest = out / target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")
        print_info(f"Tests ({target}): {out / target}")

    print_success(f"Kit written to {out.absolute()}")
    logger.info(f"Crawl kit for {package}: {len(result.screens)} screens -> {out}")
