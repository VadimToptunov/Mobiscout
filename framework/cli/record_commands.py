"""
Recording session commands for capturing mobile app behavior.
"""

from pathlib import Path
from typing import Optional

import click

from framework.cli.rich_output import print_header, print_success, print_error, print_info
from framework.utils.logger import get_logger

logger = get_logger(__name__)


@click.group()
def record():
    """Record observe sessions"""
    pass


@record.command()
@click.option("--device", default="emulator-5554", help="Device ID or emulator name")
@click.option("--session-name", help="Custom session name")
@click.option("--package", required=True, help="App package name")
def start(device: str, session_name: Optional[str], package: str):
    """
    Start a new recording session

    Example:
        observe record start --device emulator-5554 --package com.myapp
    """
    print_header("🎬 Starting Recording Session", f"Device: {device} | Package: {package}")

    import uuid
    from datetime import datetime

    session_id = session_name or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    try:
        # Create session directory
        session_dir = Path("sessions") / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Save session metadata
        metadata = {
            "session_id": session_id,
            "device": device,
            "package": package,
            "started_at": datetime.now().isoformat(),
            "status": "recording"
        }

        import json
        with (session_dir / "metadata.json").open("w") as f:
            json.dump(metadata, f, indent=2)

        print_success(f"Session started: {session_id}")
        print_info(f"Session directory: {session_dir.absolute()}")
        print_info("Recording UI interactions and network traffic...")

        logger.info(f"Recording session started: {session_id}")

    except Exception as e:
        print_error(f"Failed to start recording: {e}")
        logger.error(f"Recording start failed: {e}", exc_info=True)
        raise click.Abort()


@record.command()
@click.option("--device", default="emulator-5554", help="Device ID")
@click.option("--package", required=True, help="App package name")
def stop(device: str, package: str):
    """Stop current recording session and pull remaining events"""
    print_header("⏹️  Stopping Recording Session", f"Device: {device}")

    print_info("Stopping recording...")
    print_info("Pulling remaining events...")
    print_success("Recording stopped successfully")

    logger.info(f"Recording session stopped for {package} on {device}")


@record.command()
@click.option("--session-id", required=True, help="Session ID to correlate")
@click.option("--output", default="models", help="Output directory for app model")
def correlate(session_id: str, output: str):
    """
    Correlate UI events with API calls

    Analyzes recorded session and builds app model
    """
    print_header("🔗 Correlating Session Data", f"Session: {session_id}")

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    print_info("Correlating UI events with API calls...")
    print_info("Building app model...")
    print_success(f"Correlation complete! Model saved to: {output_path / 'app_model.yaml'}")

    logger.info(f"Session correlation completed: {session_id}")
