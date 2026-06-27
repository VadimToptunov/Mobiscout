"""
Notification system for test results

Sends notifications via multiple channels:
- Slack
- Microsoft Teams
- Email
"""

from .notifiers import SlackNotifier, TeamsNotifier, EmailNotifier, NotificationManager

__all__ = [
    "SlackNotifier",
    "TeamsNotifier",
    "EmailNotifier",
    "NotificationManager",
]
