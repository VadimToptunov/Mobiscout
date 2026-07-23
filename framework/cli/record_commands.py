"""
`mobiscout record` — capture a live manual session into a runnable test.

Streams the device's touch events, resolves each tap to the element under it, and
on Ctrl+C emits a test in the chosen target. HTTP mocking of the session's API
traffic is a separate concern — see `mobiscout mock record`.
"""

from typing import Any, Optional

import click

from framework.cli.rich_output import print_header, print_success, print_error, print_info
from framework.utils.logger import get_logger

logger = get_logger(__name__)


@click.command()
@click.option("--package", required=True, help="App under test (Android package)")
@click.option("--serial", default=None, help="adb device serial (default: the only connected device)")
@click.option("--target", default="python_pytest", help="Codegen target for the recorded test")
@click.option("--output", default="recorded-kit", help="Output directory for the test kit")
@click.option("--platform", default="android", type=click.Choice(["android"]), help="Platform (Android only)")
@click.option("--app-activity", default=None, help="Android entry activity (for the generated setup)")
@click.option("--no-launch", is_flag=True, help="Don't auto-launch the app before recording")
def record(
    package: str,
    serial: Optional[str],
    target: str,
    output: str,
    platform: str,
    app_activity: Optional[str],
    no_launch: bool,
) -> None:
    """
    Record a live session and generate a test from your taps.

    Point at a running app, interact by hand, then press Ctrl+C — each tap becomes
    a step with a ranked, self-healing locator. Text input is not captured (add it
    by editing the test). Example:

        mobiscout record --package com.myapp --target python_pytest
    """
    from framework.recorder import SessionRecorder

    print_header("🎬 Recording session", f"{package} ({platform})")

    recorder = SessionRecorder(package=package, serial=serial, platform=platform)

    if not no_launch:
        try:
            recorder._run("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
        except Exception as e:  # best-effort; recording still works if already foregrounded
            logger.warning(f"Could not auto-launch {package}: {e}")

    print_info("Interact with the app now. Each tap is captured as a step.")
    print_info("Press Ctrl+C to stop and generate the test.\n")

    def _on_step(step: Any) -> None:
        loc = step.selector.value if step.selector else "?"
        print_info(f"  • tap {step.description or loc}")

    try:
        recorder.record(on_step=_on_step)
    except KeyboardInterrupt:
        print_info("\nStopping recording...")
    except (RuntimeError, OSError) as e:
        print_error(f"Recording failed: {e}")
        raise click.Abort()

    summary = recorder.emit(output, target=target, app_activity=app_activity)

    if summary["steps"] == 0:
        print_error("No taps resolved to elements — nothing to generate.")
        if summary.get("skipped"):
            print_info(f"({summary['skipped']} tap(s) landed outside any locatable element.)")
        return

    skipped = f" ({summary['skipped']} unresolved)" if summary.get("skipped") else ""
    print_success(f"Recorded {summary['steps']} step(s){skipped} → {summary['target']}")
    print_info(f"Test kit written to: {summary['output']}")
    logger.info(f"Recording complete: {summary['steps']} steps for {package}")
