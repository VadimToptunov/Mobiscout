"""
Notification CLI commands

Commands for sending test notifications to various channels.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import click

from framework.cli.rich_output import print_header, print_info, print_success, print_error
from framework.notifications.notifiers import (
    SlackNotifier,
    TeamsNotifier,
    EmailNotifier,
    NotificationManager,
    TestSummary
)
from framework.reporting.junit_parser import JUnitParser

# Configuration file path
CONFIG_FILE = Path.home() / '.observe' / 'config.json'


def load_config() -> Dict[str, Any]:
    """Load configuration from file."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


@click.group(name='notify')
def notify() -> None:
    """🔔 Notification commands"""
    pass


@notify.command()
@click.option('--slack-webhook', help='Slack webhook URL')
@click.option('--teams-webhook', help='Teams webhook URL')
@click.option('--email-smtp', help='SMTP server (host:port)')
@click.option('--email-from', help='Sender email address')
@click.option('--email-to', help='Recipient email addresses (comma-separated)')
def configure(
        slack_webhook: Optional[str],
        teams_webhook: Optional[str],
        email_smtp: Optional[str],
        email_from: Optional[str],
        email_to: Optional[str]
) -> None:
    """Configure notification channels"""
    print_header("Configure Notifications")

    cfg = load_config()
    updated = False

    if slack_webhook:
        cfg['notification_slack_webhook'] = slack_webhook
        print_success("✅ Slack webhook configured")
        updated = True

    if teams_webhook:
        cfg['notification_teams_webhook'] = teams_webhook
        print_success("✅ Teams webhook configured")
        updated = True

    if email_smtp and email_from and email_to:
        cfg['notification_email_smtp'] = email_smtp
        cfg['notification_email_from'] = email_from
        cfg['notification_email_to'] = email_to
        print_success("✅ Email configured")
        updated = True
    elif email_smtp or email_from or email_to:
        print_error("Email configuration requires all three options: --email-smtp, --email-from, --email-to")
        raise click.Abort()

    if updated:
        save_config(cfg)
        print_info("\nConfiguration saved. Test it with: observe notify test")
    else:
        print_error("No configuration provided")
        print_info("\nUsage examples:")
        print_info("  observe notify configure --slack-webhook https://hooks.slack.com/...")
        print_info("  observe notify configure --teams-webhook https://outlook.office.com/webhook/...")
        raise click.Abort()


@notify.command()
@click.option('--channel', default='all', help='Channel to test (slack/teams/email/all)')
def test(channel: str) -> None:
    """Test notification configuration"""
    print_header(f"Test Notifications ({channel})")

    cfg = load_config()
    manager = NotificationManager()
    added_channels = []

    # Add Slack
    if channel in ('slack', 'all') and cfg.get('notification_slack_webhook'):
        manager.add_notifier(SlackNotifier(cfg['notification_slack_webhook']))
        added_channels.append('Slack')
        print_info("✓ Slack notifier configured")

    # Add Teams
    if channel in ('teams', 'all') and cfg.get('notification_teams_webhook'):
        manager.add_notifier(TeamsNotifier(cfg['notification_teams_webhook']))
        added_channels.append('Teams')
        print_info("✓ Teams notifier configured")

    # Add Email
    if channel in ('email', 'all') and cfg.get('notification_email_smtp'):
        smtp_parts = cfg['notification_email_smtp'].split(':')
        smtp_host = smtp_parts[0]
        smtp_port = int(smtp_parts[1]) if len(smtp_parts) > 1 else 587

        recipients = [r.strip() for r in cfg['notification_email_to'].split(',')]

        manager.add_notifier(EmailNotifier(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            sender_email=cfg['notification_email_from'],
            recipients=recipients,
            password=cfg.get('notification_email_password')
        ))
        added_channels.append('Email')
        print_info("✓ Email notifier configured")

    if not added_channels:
        print_error(f"No {channel} notification configured")
        print_info("\nConfigure first: observe notify configure --help")
        raise click.Abort()

    # Send test notification
    test_summary = TestSummary(
        total=42,
        passed=38,
        failed=3,
        skipped=1,
        duration=125.5,
        pass_rate=90.5,
        platform="Test",
        report_url="https://example.com/report"
    )

    print_info(f"\nSending test notification to: {', '.join(added_channels)}")

    results = manager.send_all(test_summary, "🧪 Test Notification from Mobile Observe")

    # Display results
    print_info("\n📊 Results:")
    for notifier_type, success in results.items():
        if success:
            print_success(f"  ✅ {notifier_type}: Sent successfully")
        else:
            print_error(f"  ❌ {notifier_type}: Failed to send")


@notify.command()
@click.option('--junit-xml', '-j', 'junit_path', required=True, type=click.Path(exists=True),
              help='JUnit XML results file')
@click.option('--channel', default='all', help='Channel to notify (slack/teams/email/all)')
@click.option('--title', default='Test Results', help='Notification title')
@click.option('--report-url', help='URL to full test report')
@click.option('--build-url', help='URL to CI build')
@click.option('--platform', help='Platform name (e.g., Android, iOS)')
def send(
        junit_path: str,
        channel: str,
        title: str,
        report_url: Optional[str],
        build_url: Optional[str],
        platform: Optional[str]
) -> None:
    """Send test result notification"""
    print_header("Send Test Notification")

    # Parse JUnit XML
    print_info(f"Parsing: {junit_path}")
    parser = JUnitParser()
    results = parser.parse(Path(junit_path))

    if not results or not results.tests:
        print_error("No test results found in JUnit XML")
        raise click.Abort()

    # Calculate summary
    test_list = results.tests
    total = len(test_list)
    passed = len([r for r in test_list if r.status == 'passed'])
    failed = len([r for r in test_list if r.status == 'failed'])
    skipped = len([r for r in test_list if r.status == 'skipped'])
    duration = sum(r.duration for r in test_list)
    pass_rate = (passed / total * 100) if total > 0 else 0

    summary = TestSummary(
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        duration=duration,
        pass_rate=pass_rate,
        report_url=report_url,
        build_url=build_url,
        platform=platform
    )

    print_info("\n📊 Summary:")
    print_info(f"  Total: {total}")
    print_info(f"  Passed: {passed}")
    print_info(f"  Failed: {failed}")
    print_info(f"  Pass Rate: {pass_rate:.1f}%")

    # Setup notifiers
    cfg = load_config()
    manager = NotificationManager()
    added_channels = []

    if channel in ('slack', 'all') and cfg.get('notification_slack_webhook'):
        manager.add_notifier(SlackNotifier(cfg['notification_slack_webhook']))
        added_channels.append('Slack')

    if channel in ('teams', 'all') and cfg.get('notification_teams_webhook'):
        manager.add_notifier(TeamsNotifier(cfg['notification_teams_webhook']))
        added_channels.append('Teams')

    if channel in ('email', 'all') and cfg.get('notification_email_smtp'):
        smtp_parts = cfg['notification_email_smtp'].split(':')
        smtp_host = smtp_parts[0]
        smtp_port = int(smtp_parts[1]) if len(smtp_parts) > 1 else 587

        recipients = [r.strip() for r in cfg['notification_email_to'].split(',')]

        manager.add_notifier(EmailNotifier(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            sender_email=cfg['notification_email_from'],
            recipients=recipients,
            password=cfg.get('notification_email_password')
        ))
        added_channels.append('Email')

    if not added_channels:
        print_error(f"No {channel} notification configured")
        print_info("\nConfigure first: observe notify configure --help")
        raise click.Abort()

    # Send notifications
    print_info(f"\n🔔 Sending to: {', '.join(added_channels)}")

    results_dict = manager.send_all(summary, title)

    # Display results
    success_count = sum(1 for success in results_dict.values() if success)
    total_count = len(results_dict)

    if success_count == total_count:
        print_success(f"\n✅ All notifications sent successfully ({success_count}/{total_count})")
    elif success_count > 0:
        print_info(f"\n⚠️  {success_count}/{total_count} notifications sent successfully")
    else:
        print_error("\n❌ All notifications failed")

    for notifier_type, success in results_dict.items():
        status = "✅" if success else "❌"
        print_info(f"  {status} {notifier_type}")


@notify.command()
@click.option('--healing-results', '-h', required=True, type=click.Path(exists=True),
              help='Healing results JSON file')
@click.option('--channel', default='all', help='Channel to notify')
def on_healing(healing_results: str, channel: str) -> None:
    """Send notification about healing actions"""
    print_header("Send Healing Notification")

    # Load healing results
    with open(healing_results, 'r') as f:
        data = json.load(f)

    healed_count = data.get('healed_count', 0)
    failed_count = data.get('failed_count', 0)
    total_count = healed_count + failed_count

    # Create summary (abuse TestSummary for healing stats)
    summary = TestSummary(
        total=total_count,
        passed=healed_count,
        failed=failed_count,
        skipped=0,
        duration=0,
        pass_rate=(healed_count / total_count * 100) if total_count > 0 else 0
    )

    # Setup notifiers
    cfg = load_config()
    manager = NotificationManager()

    if channel in ('slack', 'all') and cfg.get('notification_slack_webhook'):
        manager.add_notifier(SlackNotifier(cfg['notification_slack_webhook']))

    if channel in ('teams', 'all') and cfg.get('notification_teams_webhook'):
        manager.add_notifier(TeamsNotifier(cfg['notification_teams_webhook']))

    # Send notifications
    title = f"🔧 Test Healing Report: {healed_count}/{total_count} selectors healed"
    results = manager.send_all(summary, title)

    # Display results
    for notifier_type, success in results.items():
        if success:
            print_success(f"✅ {notifier_type}: Sent")  # noqa: F541
        else:
            print_error(f"❌ {notifier_type}: Failed")


@notify.command(name='list')
def list_channels() -> None:
    """List configured notification channels"""
    print_header("Configured Channels")

    cfg = load_config()

    channels = []

    if cfg.get('notification_slack_webhook'):
        channels.append(('Slack', cfg['notification_slack_webhook'][:50] + '...'))

    if cfg.get('notification_teams_webhook'):
        channels.append(('Teams', cfg['notification_teams_webhook'][:50] + '...'))

    if cfg.get('notification_email_smtp'):
        channels.append(('Email', f"{cfg['notification_email_from']} → {cfg['notification_email_to']}"))

    if channels:
        for name, info in channels:
            print_success(f"✅ {name}")
            print_info(f"   {info}")
    else:
        print_info("No notification channels configured")
        print_info("\nConfigure channels: observe notify configure --help")


if __name__ == '__main__':
    notify()
