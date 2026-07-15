"""
Main CLI entry point for Mobiscout

Simplified main module that imports command groups from separate modules.
"""

import click

from framework import __version__
from framework.cli.a11y_commands import a11y

# Import command groups
from framework.cli.business_logic_commands import business
from framework.cli.fuzz_commands import fuzz
from framework.cli.verify_commands import verify
from framework.cli.ci_commands import ci
from framework.cli.config_commands import config
from framework.cli.daemon_commands import daemon_command
from framework.cli.dashboard_commands import dashboard
from framework.cli.data_commands import data
from framework.cli.device_commands import devices
from framework.cli.docs_commands import docs
from framework.cli.doctor_command import doctor
from framework.cli.execute_commands import execute
from framework.cli.generate_commands import generate
from framework.cli.crawl_commands import crawl
from framework.cli.healing_commands import heal
from framework.cli.load_commands import load
from framework.cli.ml_commands import ml
from framework.cli.mock_commands import mock
from framework.cli.notify_commands import notify
from framework.cli.observability_commands import observe_ as observability
from framework.cli.parallel_commands import parallel
from framework.cli.perf_commands import perf
from framework.cli.project_commands import project
from framework.cli.record_commands import record
from framework.cli.report_commands import report
from framework.cli.rich_output import print_banner
from framework.cli.security_commands import security
from framework.cli.selection_commands import select
from framework.cli.selector_commands import selector
from framework.cli.visual_commands import visual


@click.group()
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx):
    """
    📱 Mobiscout

    Intelligent Mobile Testing Platform - Scout, Analyze, Automate
    """
    ctx.ensure_object(dict)


# Register command groups
cli.add_command(business)
cli.add_command(project)
cli.add_command(record)
cli.add_command(generate)
cli.add_command(crawl)
cli.add_command(dashboard)
cli.add_command(heal)
cli.add_command(devices)
cli.add_command(ml)
cli.add_command(security)
cli.add_command(perf)
cli.add_command(select)
cli.add_command(config)
cli.add_command(notify)
cli.add_command(visual)
cli.add_command(data)
cli.add_command(execute)
cli.add_command(mock)
cli.add_command(selector)
cli.add_command(parallel)
cli.add_command(ci)
cli.add_command(doctor)
cli.add_command(report)
cli.add_command(observability, name="observe")
cli.add_command(a11y)
cli.add_command(load)
cli.add_command(docs)
cli.add_command(daemon_command, name="daemon")
cli.add_command(fuzz)
cli.add_command(verify)


@cli.command()
def info():
    """Show framework information"""
    print_banner()
    click.echo("\n📦 Framework Information")
    click.echo(f"   Version: {__version__}")
    click.echo("   Platform: Mobile (Android & iOS)")
    click.echo("\n✨ Features:")
    click.echo("   • Business Logic Analysis")
    click.echo("   • Project Integration")
    click.echo("   • Session Recording")
    click.echo("   • Test Generation")
    click.echo("   • Self-Healing Tests")
    click.echo("   • Device Management")
    click.echo("   • Dashboard & Analytics")
    click.echo("   • Rich CLI Interface")
    click.echo("\n📚 Documentation: See README.md")
    click.echo("🐛 Issues: https://github.com/VadimToptunov/Mobiscout/issues")


if __name__ == "__main__":
    cli()
