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
@click.option("--max-steps", default=40, show_default=True, help="Crawl step budget")
@click.option("--max-depth", default=8, show_default=True, help="Crawl depth budget")
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
    max_steps,
    max_depth,
):
    """
    Crawl a running app and export an element inventory + tests.

    Android over adb (default) or over an Appium/UiAutomator2 session
    (--driver appium, which unlocks real devices and cloud grids via --cap), and
    iOS over an Appium/XCUITest session.

    Examples:
        observe crawl --package com.example.app --targets python_pytest,java_testng
        observe crawl --package com.example.app --driver appium --udid <UDID>
        observe crawl --platform ios --package com.apple.Preferences --udid <UDID>
    """
    from framework.codegen import available_targets, get_emitter
    from framework.crawler import AdbCrawlerDriver, AndroidAppiumDriver, AppCrawler, IOSCrawlerDriver, build_test_model
    from framework.crawler.classify import ensure_model
    from framework.crawler.graph import build_graph, to_dot, to_json, to_mermaid
    from framework.crawler.report import inventory_json_str, inventory_markdown

    print_header("🕷️  Crawling app", f"{package} ({platform})")

    # Provision the element-classification model (trains from synthetic data in
    # ~1s on first run, then cached). Never fatal: falls back to the heuristic.
    if ensure_model() is None:
        print_info("Element typing: using the rule heuristic (ML model unavailable).")

    extra_caps = dict(c.split("=", 1) for c in caps if "=" in c)
    appium_session = None  # any Appium-owned driver we must quit() at the end
    if platform == "ios":
        try:
            crawl_driver = IOSCrawlerDriver(
                bundle_id=package, udid=udid, device_name=device_name or "iPhone 17", server=server
            )
        except Exception as e:
            print_error(f"Could not open an Appium iOS session ({e}). Is the Appium server running at {server}?")
            raise click.Abort()
        appium_session = crawl_driver
    elif driver == "appium":
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
            print_error(f"Could not open an Appium Android session ({e}). Is the Appium server running at {server}?")
            raise click.Abort()
        appium_session = crawl_driver
    else:
        crawl_driver = AdbCrawlerDriver(serial=serial)

    current = crawl_driver.current_package()
    if current != package:
        hint = (
            f"adb shell monkey -p {package} -c android.intent.category.LAUNCHER 1"
            if platform == "android"
            else f"xcrun simctl launch booted {package}"
        )
        print_error(f"App '{package}' is not in the foreground (found '{current}'). Launch it first: {hint}")
        if appium_session:
            appium_session.quit()
        raise click.Abort()

    try:
        result = AppCrawler(crawl_driver, package, max_steps=max_steps, max_depth=max_depth).crawl()
    finally:
        if appium_session:
            appium_session.quit()
    print_success(f"Discovered {len(result.screens)} screen(s), {len(result.transitions)} transition(s)")

    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)

    # 1) Element inventory (Markdown + JSON) — the tester-facing map.
    (out / "inventory.md").write_text(inventory_markdown(result, package), encoding="utf-8", newline="\n")
    (out / "inventory.json").write_text(inventory_json_str(result, package), encoding="utf-8", newline="\n")
    print_info(f"Inventory: {out / 'inventory.md'}")

    # 2) Interaction graph — Mermaid (renders on GitHub), Graphviz DOT, JSON.
    graph = build_graph(result, package)
    (out / "graph.mmd").write_text(to_mermaid(graph), encoding="utf-8", newline="\n")
    (out / "graph.dot").write_text(to_dot(graph), encoding="utf-8", newline="\n")
    (out / "graph.json").write_text(to_json(graph), encoding="utf-8", newline="\n")
    gm = graph.metrics()
    print_info(f"Graph: {gm['screens']} screens, {gm['transitions']} transitions, {gm['dead_ends']} dead-end(s)")

    # 3) Tests in each requested language.
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
