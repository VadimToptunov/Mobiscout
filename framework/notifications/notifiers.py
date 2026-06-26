"""
Notification providers

Send test result notifications via various channels.
"""

import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

import requests


@dataclass
class TestSummary:
    """Test execution summary for notifications"""
    total: int
    passed: int
    failed: int
    skipped: int
    duration: float
    pass_rate: float
    report_url: Optional[str] = None
    platform: Optional[str] = None
    build_url: Optional[str] = None


class Notifier(ABC):
    """Base class for notifiers"""

    @abstractmethod
    def send(self, summary: TestSummary, title: str = "Test Results") -> bool:
        """
        Send notification

        Args:
            summary: Test execution summary
            title: Notification title

        Returns:
            True if successful, False otherwise
        """
        pass


class SlackNotifier(Notifier):
    """
    Slack webhook notifier
    """

    def __init__(self, webhook_url: str):
        """
        Initialize Slack notifier

        Args:
            webhook_url: Slack incoming webhook URL
        """
        self.webhook_url = webhook_url

    def send(self, summary: TestSummary, title: str = "Test Results") -> bool:
        """Send notification to Slack"""
        try:
            # Determine color based on pass rate
            if summary.pass_rate >= 95:
                color = "#36a64"  # Green
            elif summary.pass_rate >= 80:
                color = "#ff9900"  # Orange
            else:
                color = "#d00000"  # Red

            # Build message
            message = {
                "text": f"*{title}*",
                "attachments": [
                    {
                        "color": color,
                        "fields": [
                            {
                                "title": "Total Tests",
                                "value": str(summary.total),
                                "short": True
                            },
                            {
                                "title": "Pass Rate",
                                "value": f"{summary.pass_rate:.1f}%",
                                "short": True
                            },
                            {
                                "title": "Passed",
                                "value": f"{summary.passed}",
                                "short": True
                            },
                            {
                                "title": "Failed",
                                "value": f"{summary.failed}",
                                "short": True
                            },
                            {
                                "title": "Skipped",
                                "value": str(summary.skipped),
                                "short": True
                            },
                            {
                                "title": "Duration",
                                "value": f"{summary.duration:.1f}s",
                                "short": True
                            }
                        ]
                    }
                ]
            }

            # Add platform if available
            if summary.platform:
                message["attachments"][0]["fields"].insert(0, {
                    "title": "Platform",
                    "value": summary.platform,
                    "short": True
                })

            # Add report link if available
            if summary.report_url:
                message["attachments"][0]["actions"] = [
                    {
                        "type": "button",
                        "text": "View Report",
                        "url": summary.report_url
                    }
                ]

            # Send to Slack
            response = requests.post(
                self.webhook_url,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()

            return True

        except (requests.RequestException, KeyError, ValueError, OSError) as e:
            print(f"Error sending Slack notification: {e}")
            return False


class TeamsNotifier(Notifier):
    """
    Microsoft Teams webhook notifier
    """

    def __init__(self, webhook_url: str):
        """
        Initialize Teams notifier

        Args:
            webhook_url: Teams incoming webhook URL
        """
        self.webhook_url = webhook_url

    def send(self, summary: TestSummary, title: str = "Test Results") -> bool:
        """Send notification to Microsoft Teams"""
        try:
            # Determine theme color based on pass rate
            if summary.pass_rate >= 95:
                theme_color = "28a745"  # Green
            elif summary.pass_rate >= 80:
                theme_color = "ffc107"  # Yellow
            else:
                theme_color = "dc3545"  # Red

            # Build message card
            message = {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "summary": title,
                "themeColor": theme_color,
                "title": title,
                "sections": [
                    {
                        "activityTitle": "Test Execution Summary",
                        "facts": [
                            {"name": "Total Tests", "value": str(summary.total)},
                            {"name": "Passed", "value": f"{summary.passed}"},
                            {"name": "Failed", "value": f"{summary.failed}"},
                            {"name": "Skipped", "value": str(summary.skipped)},
                            {"name": "Pass Rate", "value": f"{summary.pass_rate:.1f}%"},
                            {"name": "Duration", "value": f"{summary.duration:.1f}s"}
                        ]
                    }
                ]
            }

            # Add platform if available
            if summary.platform:
                message["sections"][0]["facts"].insert(0, {
                    "name": "Platform",
                    "value": summary.platform
                })

            # Add potential actions
            if summary.report_url or summary.build_url:
                message["potentialAction"] = []

                if summary.report_url:
                    message["potentialAction"].append({
                        "@type": "OpenUri",
                        "name": "View Report",
                        "targets": [{"os": "default", "uri": summary.report_url}]
                    })

                if summary.build_url:
                    message["potentialAction"].append({
                        "@type": "OpenUri",
                        "name": "View Build",
                        "targets": [{"os": "default", "uri": summary.build_url}]
                    })

            # Send to Teams
            response = requests.post(
                self.webhook_url,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()

            return True

        except (requests.RequestException, KeyError, ValueError, OSError) as e:
            print(f"Error sending Teams notification: {e}")
            return False


class EmailNotifier(Notifier):
    """
    Email notifier
    """

    def __init__(
            self,
            smtp_host: str,
            smtp_port: int,
            sender_email: str,
            recipients: List[str],
            username: Optional[str] = None,
            password: Optional[str] = None,
            use_tls: bool = True
    ):
        """
        Initialize email notifier

        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            sender_email: Sender email address
            recipients: List of recipient email addresses
            username: SMTP username (optional)
            password: SMTP password (optional)
            use_tls: Use TLS encryption
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.recipients = recipients
        self.username = username or sender_email
        self.password = password
        self.use_tls = use_tls

    def send(self, summary: TestSummary, title: str = "Test Results") -> bool:
        """Send email notification"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = title
            msg['From'] = self.sender_email
            msg['To'] = ', '.join(self.recipients)

            # Build HTML body
            # status_color =  # Unused "#28a745" if summary.pass_rate >= 80 else "#dc3545"

            html_body = """
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: {status_color}; color: white; padding: 20px; border-radius: 5px; }}
                    .stats {{ margin: 20px 0; }}
                    .stat {{ display: inline-block; margin: 10px 20px 10px 0; }}
                    .stat-label {{ font-size: 12px; color: #666; }}
                    .stat-value {{ font-size: 24px; font-weight: bold; }}
                    .button {{ display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>{title}</h2>
                    </div>
                    <div class="stats">
                        <div class="stat">
                            <div class="stat-label">Total Tests</div>
                            <div class="stat-value">{summary.total}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">Passed</div>
                            <div class="stat-value" style="color: #28a745;">{summary.passed}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">Failed</div>
                            <div class="stat-value" style="color: #dc3545;">{summary.failed}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">Skipped</div>
                            <div class="stat-value" style="color: #ffc107;">{summary.skipped}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">Pass Rate</div>
                            <div class="stat-value">{summary.pass_rate:.1f}%</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">Duration</div>
                            <div class="stat-value">{summary.duration:.1f}s</div>
                        </div>
                    </div>
"""

            if summary.report_url:
                html_body += """
                    <a href="{summary.report_url}" class="button">View Full Report</a>
"""

            html_body += """
                </div>
            </body>
            </html>
            """

            # Attach HTML body
            msg.attach(MIMEText(html_body, 'html'))

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                if self.password:
                    server.login(self.username, self.password)
                server.send_message(msg)

            return True

        except (smtplib.SMTPException, OSError, ValueError) as e:
            print(f"Error sending email notification: {e}")
            return False


class NotificationManager:
    """
    Manages multiple notification channels
    """

    def __init__(self):
        self.notifiers: List[Notifier] = []

    def add_notifier(self, notifier: Notifier):
        """Add a notifier"""
        self.notifiers.append(notifier)

    def send_all(self, summary: TestSummary, title: str = "Test Results") -> Dict[str, bool]:
        """
        Send notifications to all configured channels

        Returns:
            Dictionary mapping notifier type to success status
        """
        results = {}
        for notifier in self.notifiers:
            notifier_type = type(notifier).__name__
            results[notifier_type] = notifier.send(summary, title)
        return results
