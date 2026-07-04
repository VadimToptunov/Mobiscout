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
@click.option("--package", required=True, help="App package under test, e.g. com.example.app")
@click.option("--serial", default=None, help="adb device serial (default: the only connected device)")
@click.option("--output", default="crawl-kit", help="Output directory for the artifacts")
@click.option("--targets", default="python_pytest", help="Comma-separated codegen targets for the tests")
@click.option("--app-activity", default=None, help="Android entry activity (for the generated test setup)")
@click.option("--max-steps", default=40, show_default=True, help="Crawl step budget")
@click.option("--max-depth", default=8, show_default=True, help="Crawl depth budget")
def crawl(package, serial, output, targets, app_activity, max_steps, max_depth):
    """
    Crawl a running app and export an element inventory + tests.

    Example:
        observe crawl --package com.example.app --targets python_pytest,java_testng
    """
    from framework.codegen import available_targets, get_emitter
    from framework.crawler import AdbCrawlerDriver, AppCrawler, build_test_model
    from framework.crawler.report import inventory_json_str, inventory_markdown

    print_header("🕷️  Crawling app", package)

    driver = AdbCrawlerDriver(serial=serial)
    if driver.current_package() != package:
        print_error(
            f"App '{package}' is not in the foreground (found '{driver.current_package()}'). "
            f"Launch it first: adb shell monkey -p {package} -c android.intent.category.LAUNCHER 1"
        )
        raise click.Abort()

    result = AppCrawler(driver, package, max_steps=max_steps, max_depth=max_depth).crawl()
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
