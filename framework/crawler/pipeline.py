"""
Parameterized crawl → kit — one config in, artifacts out.

This is the single entry point behind both the CLI (`mobiscout crawl`) and the IDE
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

from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.codegen import available_targets, get_emitter
from framework.crawler.app_crawler import AppCrawler, CrawlResult
from framework.crawler.graph import build_graph, to_dot, to_json, to_mermaid
from framework.crawler.report import inventory_json_str, inventory_markdown
from framework.crawler.to_codegen import build_test_model

_DEFAULT_TARGETS = ["python_pytest"]


def _cap_screens(result: CrawlResult, limit: int) -> CrawlResult:
    """Trim a crawl result to at most ``limit`` screens (keeping insertion order),
    dropping transitions that touch a removed screen so every downstream artifact
    (graph, inventory, model) is built from one consistent set. Returns ``result``
    unchanged when already within the limit — so the open-core / PRO unlimited tier
    pays nothing. New instance (``replace``): never mutates the caller's result."""
    if limit >= len(result.screens):
        return result
    kept = list(result.screens)[:limit]
    kept_set = set(kept)
    return replace(
        result,
        screens={fp: result.screens[fp] for fp in kept},
        transitions=[t for t in result.transitions if t[0] in kept_set and t[2] in kept_set],
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def build_kit(result: CrawlResult, config: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a crawl into the full artifact kit per the config. Device-free."""
    package = config["package"]
    out = Path(config.get("output", "crawl-kit"))
    out.mkdir(parents=True, exist_ok=True)

    # Entitlement quota (open-core seam): the free tier maps at most N screens per
    # crawl. Trim the result up front so the graph, inventory and model are all
    # built from the capped set. No-op on the unlimited (open-core / PRO) tier.
    from framework.licensing import cap_screens, cap_tests

    result = _cap_screens(result, cap_screens(len(result.screens)))

    # Build the interaction graph once and thread it through every consumer
    # (inventory, graph writers, and the test model, which would otherwise rebuild
    # it several more times). The graph is deterministic for a given result, so the
    # artifacts are byte-identical — this is purely fewer rebuilds.
    graph = build_graph(result, package)

    _write(out / "inventory.md", inventory_markdown(result, package, graph=graph))
    _write(out / "inventory.json", inventory_json_str(result, package))

    _write(out / "graph.mmd", to_mermaid(graph))
    _write(out / "graph.dot", to_dot(graph))
    _write(out / "graph.json", to_json(graph))

    # Structural findings read off the graph (unreachable / dead-end / no-return).
    from framework.crawler.invariants import check_invariants, invariants_markdown

    _write(out / "invariants.md", invariants_markdown(graph))
    invariant_count = len(check_invariants(graph))

    model = build_test_model(
        result,
        app_package=package,
        app_activity=config.get("app_activity"),
        launch_args=config.get("process_args"),
        graph=graph,
        waypoints=config.get("waypoints"),
    )

    # Only-new mode: drop cases already covered by the team's existing tests, so a
    # crawl of a new feature yields tests for just that feature. A premium (team/CI)
    # feature — gated by ``has_feature`` so a limited tier falls back to the full kit;
    # a no-op on the open-core (unlimited) tier, which has every feature.
    from framework.licensing import has_feature

    gap = None
    if config.get("only_new") and has_feature("incremental"):
        from framework.crawler.coverage import existing_test_text, filter_to_new

        covered = existing_test_text(Path(config.get("existing_tests", "")))
        model, report = filter_to_new(model, covered)
        gap = report.summary()
        _write(out / "coverage_gap.txt", gap + "\n" + "\n".join(f"- {n}" for n in report.new_case_names) + "\n")

    # Entitlement quota: cap generated test cases for the free tier (after only-new
    # filtering, so the final kit carries at most N cases). No-op when unlimited.
    model.cases = model.cases[: cap_tests(len(model.cases))]

    target_ids = {t.id for t in available_targets()}
    from framework.licensing import allow_targets

    # No-op on the open-core (unlimited) tier; a paid layer can cap the languages.
    targets: List[str] = allow_targets([t for t in (config.get("targets") or _DEFAULT_TARGETS) if t])
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

    # API tests from network traffic captured during the same session (a proxy
    # HAR — mitmproxy/Charles). The crawl produces the UI tests; the capture adds
    # contract tests for the endpoints the app actually called, in one kit. A premium
    # feature — gated by ``has_feature`` (no-op on the unlimited open-core tier).
    api_tests = emit_api_tests_from_har(config.get("har"), out) if has_feature("api_contract_tests") else 0
    # Mock layer: replay the same captured traffic deterministically, so the
    # generated tests (and a re-crawl) don't depend on a live/flaky backend.
    mocks = emit_mock_from_har(config.get("har"), out)
    # Deeplinks the app declares — listed in the kit so a tester knows the
    # shortcuts into deep screens (the crawl also seeds from them, see _seed_deeplinks).
    from framework.crawler.deeplinks import deeplinks_markdown, extract_deeplinks

    deeplinks = extract_deeplinks(config)
    _write(out / "deeplinks.md", deeplinks_markdown(deeplinks, package))

    return {
        "package": package,
        "platform": model.platform.value,
        "screens": len(result.screens),
        "transitions": len(result.transitions),
        "cases": len(model.cases),
        "api_tests": api_tests,
        "mocks": mocks,
        "deeplinks": len(deeplinks),
        "targets": written,
        "scaffolded": scaffolded,
        "gap": gap,
        "invariants": invariant_count,
        "output": str(out.absolute()),
    }


def emit_api_tests_from_har(har: Optional[str], out: Path) -> int:
    """Write ``test_api.py`` into the kit at ``out`` from a captured proxy HAR,
    returning the number of endpoints covered (0 when no HAR is given or it holds
    no modelled calls). Shared by both kit writers (``build_kit`` and the crawl
    CLI's ``write_kit``) so a crawl + capture yields UI *and* API tests."""
    if not har:
        return 0
    from types import SimpleNamespace

    from framework.api_analyzer.har import load_har_calls
    from framework.codegen.api_test import emit_api_tests
    from framework.codegen.source_api_adapter import base_url_from_har, har_calls_to_api_calls

    har_calls = load_har_calls(Path(har))
    api_calls = har_calls_to_api_calls(har_calls)
    if not api_calls:
        return 0
    app_model: Any = SimpleNamespace(api_calls={c.name: c for c in api_calls})
    for name, content in emit_api_tests(app_model, base_url=base_url_from_har(har_calls)).items():
        _write(out / name, content)
    return len(api_calls)


def emit_mock_from_har(har: Optional[str], out: Path) -> int:
    """Write the mock layer (``mock/mock_server.py`` + ``recordings.json`` + a
    README) into the kit from a captured proxy HAR, returning the number of routes
    recorded (0 when no HAR is given or it holds no responses). A deterministic
    replay of the traffic the crawl actually saw."""
    if not har:
        return 0
    from framework.api_analyzer.har import load_har_calls
    from framework.codegen.mock_server import build_recordings, emit_mock_server
    from framework.codegen.source_api_adapter import base_url_from_har

    har_calls = load_har_calls(Path(har))
    files = emit_mock_server(har_calls, base_url=base_url_from_har(har_calls))
    if not files:
        return 0
    for name, content in files.items():
        _write(out / "mock" / name, content)
    return len(build_recordings(har_calls))


def _make_driver(config: Dict[str, Any]) -> Any:
    """Build a crawler driver from the config; returns (driver, owns_session)."""
    package = config["package"]
    platform = config.get("platform", "android")
    server = config.get("server", "http://localhost:4723")
    if platform == "ios":
        from framework.crawler.appium_driver import IOSCrawlerDriver

        drv: Any = IOSCrawlerDriver(
            bundle_id=package,
            udid=config.get("udid"),
            device_name=config.get("device_name") or "iPhone 17",
            server=server,
            process_args=config.get("process_args"),
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


def _merge_results(into: CrawlResult, extra: CrawlResult) -> CrawlResult:
    """Fold a seed crawl's screens/transitions into the main result — union screens
    by fingerprint, append not-yet-seen transitions (keyed by src/label/dst since a
    CrawlElement isn't hashable), sum steps."""
    for fingerprint, screen in extra.screens.items():
        into.screens.setdefault(fingerprint, screen)
    seen = {(src, el.label, dst) for src, el, dst in into.transitions}
    for src, el, dst in extra.transitions:
        key = (src, el.label, dst)
        if key not in seen:
            into.transitions.append((src, el, dst))
            seen.add(key)
    into.steps += extra.steps
    return into


def _seed_deeplinks(config: Dict[str, Any], driver: Any, result: CrawlResult, waypoints: List[Any]) -> CrawlResult:
    """Open each configured/extracted deeplink as an extra crawl root and merge the
    screens it reaches into ``result`` — coverage a tap-only walk can't reach. No-op
    when there are no deeplinks or the driver can't open one."""
    from framework.crawler.deeplinks import extract_deeplinks

    seeds = extract_deeplinks(config)
    if not seeds or not hasattr(driver, "open_url"):
        return result
    package = config["package"]
    steps = int(config.get("seed_max_steps", config.get("max_steps", 40)))
    depth = int(config.get("max_depth", 8))
    seconds = float(config.get("seed_max_seconds", 60) or 0)
    for uri in seeds:
        try:
            if not driver.open_url(uri, package=package):
                continue  # opened a browser / another app, or failed — skip it
        except Exception:
            continue
        seeded = AppCrawler(
            driver, package, max_steps=steps, max_depth=depth, waypoints=waypoints, max_seconds=seconds
        ).crawl()
        result = _merge_results(result, seeded)
    return result


def _crawl(config: Dict[str, Any], driver: Any = None) -> CrawlResult:
    """Crawl the app described by ``config`` (or use an injected ``driver``),
    passing any configured gates. Shared by run_kit and crawl_graph."""
    owns = False
    if driver is None:
        driver, owns = _make_driver(config)
    # Gate-passing instructions (login/OTP/biometric/permission) as JSON dicts from
    # the CLI/plugin -> Waypoint objects, so the crawl explores behind gates.
    from framework.crawler.waypoints import Waypoint

    waypoints = [Waypoint(**w) for w in config.get("waypoints") or []]
    try:
        # Opt-in device prep (grant permissions / reset state) before exploring;
        # self-gates on ``grant_permissions`` / ``reset_state`` and no-ops otherwise.
        from framework.devices.prepare import prepare_device

        prepare_device(config)
        result = AppCrawler(
            driver,
            config["package"],
            max_steps=int(config.get("max_steps", 40)),
            max_depth=int(config.get("max_depth", 8)),
            waypoints=waypoints,
            max_seconds=float(config.get("max_seconds", 0) or 0),
        ).crawl()
        # Extra entry way: seed the graph from deeplinks the UI walk can't reach.
        return _seed_deeplinks(config, driver, result, waypoints)
    finally:
        if owns and hasattr(driver, "quit"):
            driver.quit()


def _ios_crashes(config: Dict[str, Any], since: float) -> "List[tuple[str, bytes]]":
    """iOS crash reports (``.ips``) for the app that landed during the crawl window.

    Scans the standard DiagnosticReports locations (host + per-simulator) for
    ``<AppExecutable>-*.ips`` files newer than ``since``.
    """
    app = config.get("app_name") or str(config.get("package", "")).rsplit(".", 1)[-1]
    if not app:
        return []
    home = Path.home()
    roots = [home / "Library" / "Logs" / "DiagnosticReports"]
    udid = config.get("udid")
    if udid:
        roots.append(
            home
            / "Library"
            / "Developer"
            / "CoreSimulator"
            / "Devices"
            / udid
            / "data"
            / "Library"
            / "Logs"
            / "DiagnosticReports"
        )
    cutoff = since - 5.0  # the report lands a beat after the crash
    out: "List[tuple[str, bytes]]" = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for f in root.glob(f"{app}-*.ips"):
                if f.is_file() and f.stat().st_mtime >= cutoff:
                    out.append((f.name, f.read_bytes()))
        except OSError:
            continue
    return out


def _android_crashes(config: Dict[str, Any], since: float) -> "List[tuple[str, bytes]]":
    """Android crashes for the app from logcat's dedicated crash buffer, limited to
    the crawl window. Returns a single aggregated ``<package>-logcat-crash.txt`` when
    a fatal exception for the app was logged, else nothing."""
    import subprocess
    import time

    serial = config.get("udid") or config.get("serial")
    package = config.get("package")
    if not serial:
        return []
    since_arg = time.strftime("%m-%d %H:%M:%S.000", time.localtime(since))
    try:
        r = subprocess.run(
            ["adb", "-s", serial, "logcat", "-b", "crash", "-d", "-v", "time", "-t", since_arg],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    text = r.stdout
    if not text.strip() or "FATAL EXCEPTION" not in text:
        return []
    # Keep it if the app is implicated (or when we can't tell, keep it — the crash
    # buffer only holds crashes anyway).
    if package and package not in text and "beginning of crash" not in text:
        return []
    name = f"{(package or 'app').replace('/', '_')}-logcat-crash.txt"
    return [(name, text.encode("utf-8"))]


def _collect_crashes(config: Dict[str, Any], since: float) -> "List[tuple[str, bytes]]":
    """Crash artifacts the app dropped during the crawl, as ``(filename, bytes)``.

    A crash leaves the app but no test — so without this the kit silently loses the
    single most useful signal ("it crashed on screen N"). iOS reads ``.ips`` reports;
    Android reads logcat's crash buffer. Best-effort: any error yields no crashes
    rather than failing the kit.
    """
    platform = config.get("platform", "android")
    try:
        if platform == "ios":
            return _ios_crashes(config, since)
        if platform == "android":
            return _android_crashes(config, since)
    except Exception:
        return []
    return []


def run_kit(config: Dict[str, Any], driver: Any = None) -> Dict[str, Any]:
    """Crawl the app described by ``config`` (or use an injected ``driver``) and
    build the kit. The one call the CLI and the IDE plugin both drive.

    Also collects any crash the app dropped during the crawl (iOS ``.ips`` reports
    or Android logcat crashes) into the kit's ``crashes/`` folder, so "the app
    crashed while crawling" is a first-class artifact rather than a silent gap.
    """
    import time

    started = time.time()
    summary = build_kit(_crawl(config, driver), config)

    crashes = _collect_crashes(config, started)
    if crashes:
        dest = Path(config.get("output", "crawl-kit")) / "crashes"
        dest.mkdir(parents=True, exist_ok=True)
        for name, data in crashes:
            try:
                (dest / name).write_bytes(data)
            except OSError:
                pass
    summary["crashes"] = len(crashes)
    return summary


def crawl_graph(config: Dict[str, Any], driver: Any = None) -> Dict[str, Any]:
    """Crawl and return just the interaction graph as a dict — the IDE plugin's
    ``flow/getGraph``, with no files written."""
    from framework.crawler.graph import build_graph

    return build_graph(_crawl(config, driver), config.get("package", "")).to_dict()
