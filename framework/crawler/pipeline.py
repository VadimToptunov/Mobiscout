"""
Parameterized crawl → kit — one config in, artifacts out.

This is the single entry point behind both the CLI (`observe crawl`) and the IDE
plugin: you pass a config describing *what you want* and it produces the result —
an element inventory, an interaction graph, tests in the chosen language(s), and
optionally a runnable project shell. No magic button; every knob is a parameter.

Config keys (all but ``package`` optional):

    package        app package (Android) or bundle id (iOS)          [required]
    platform       "android" | "ios"                                 [android]
    targets        list of codegen targets                           [["python_pytest"]]
    output         output directory                                  ["crawl-kit"]
    app_activity   Android entry activity
    scaffold       also write a runnable project shell (new framework) [False]
    max_steps      crawl step budget                                 [40]
    max_depth      crawl depth budget                                [8]
    serial/udid/device_name/server/extra_caps   driver connection details

    build_kit(result, config)  — device-free: turn a CrawlResult into artifacts.
    run_kit(config, driver=None)  — crawl (or use an injected driver) then build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.codegen import available_targets, get_emitter
from framework.crawler.app_crawler import AppCrawler, CrawlResult
from framework.crawler.graph import build_graph, to_dot, to_json, to_mermaid
from framework.crawler.report import inventory_json_str, inventory_markdown
from framework.crawler.to_codegen import build_test_model

_DEFAULT_TARGETS = ["python_pytest"]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def build_kit(result: CrawlResult, config: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a crawl into the full artifact kit per the config. Device-free."""
    package = config["package"]
    out = Path(config.get("output", "crawl-kit"))
    out.mkdir(parents=True, exist_ok=True)

    _write(out / "inventory.md", inventory_markdown(result, package))
    _write(out / "inventory.json", inventory_json_str(result, package))

    graph = build_graph(result, package)
    _write(out / "graph.mmd", to_mermaid(graph))
    _write(out / "graph.dot", to_dot(graph))
    _write(out / "graph.json", to_json(graph))

    model = build_test_model(result, app_package=package, app_activity=config.get("app_activity"))

    # Only-new mode: drop cases already covered by the team's existing tests, so a
    # crawl of a new feature yields tests for just that feature.
    gap = None
    if config.get("only_new"):
        from framework.crawler.coverage import existing_test_text, filter_to_new

        covered = existing_test_text(Path(config.get("existing_tests", "")))
        model, report = filter_to_new(model, covered)
        gap = report.summary()
        _write(out / "coverage_gap.txt", gap + "\n" + "\n".join(f"- {n}" for n in report.new_case_names) + "\n")

    target_ids = {t.id for t in available_targets()}
    targets: List[str] = [t for t in (config.get("targets") or _DEFAULT_TARGETS) if t]
    written: List[str] = []
    for target in targets:
        if target not in target_ids:
            continue
        for name, content in get_emitter(target).emit(model).items():
            _write(out / target / name, content)
        written.append(target)

    scaffolded: Optional[str] = None
    if config.get("scaffold") and model.cases:
        try:
            from framework.codegen.scaffold import scaffold_files

            server = config.get("server", "http://localhost:4723")
            for target in targets:
                files = scaffold_files(model, target, server=server)
                if files:
                    for rel, content in files.items():
                        _write(out / rel, content)
                    scaffolded = target
                    break
        except ImportError:
            pass

    return {
        "package": package,
        "platform": model.platform.value,
        "screens": len(result.screens),
        "transitions": len(result.transitions),
        "cases": len(model.cases),
        "targets": written,
        "scaffolded": scaffolded,
        "gap": gap,
        "output": str(out.absolute()),
    }


def _make_driver(config: Dict[str, Any]):
    """Build a crawler driver from the config; returns (driver, owns_session)."""
    package = config["package"]
    platform = config.get("platform", "android")
    server = config.get("server", "http://localhost:4723")
    if platform == "ios":
        from framework.crawler.appium_driver import IOSCrawlerDriver

        drv = IOSCrawlerDriver(
            bundle_id=package,
            udid=config.get("udid"),
            device_name=config.get("device_name") or "iPhone 17",
            server=server,
        )
        return drv, True
    if config.get("driver") == "appium":
        try:
            from framework.crawler.appium_android import AndroidAppiumDriver
        except ImportError:  # not yet available on this checkout
            pass
        else:
            drv = AndroidAppiumDriver(
                app_package=package,
                app_activity=config.get("app_activity"),
                udid=config.get("udid"),
                device_name=config.get("device_name") or "Android Device",
                server=server,
                extra_caps=config.get("extra_caps") or {},
            )
            return drv, True
    from framework.crawler.adb_driver import AdbCrawlerDriver

    return AdbCrawlerDriver(serial=config.get("serial")), False


def run_kit(config: Dict[str, Any], driver: Any = None) -> Dict[str, Any]:
    """Crawl the app described by ``config`` (or use an injected ``driver``) and
    build the kit. The one call the CLI and the IDE plugin both drive."""
    owns = False
    if driver is None:
        driver, owns = _make_driver(config)
    try:
        result = AppCrawler(
            driver,
            config["package"],
            max_steps=int(config.get("max_steps", 40)),
            max_depth=int(config.get("max_depth", 8)),
        ).crawl()
    finally:
        if owns and hasattr(driver, "quit"):
            driver.quit()
    return build_kit(result, config)
