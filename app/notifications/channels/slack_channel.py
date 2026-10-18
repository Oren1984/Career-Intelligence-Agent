# notifications/channels/slack_channel.py
# Part of the Career Intelligence Agent project.
"""Slack webhook notification channel."""
import json
import logging
from typing import Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from app.notifications.channels.base_channel import BaseChannel

logger = logging.getLogger(__name__)


class SlackChannel(BaseChannel):
    """
    Sends job notifications to a Slack channel via an Incoming Webhook.

    Config keys (from notifications.yaml under 'slack:'):
        webhook_url: Slack Incoming Webhook URL
                     (https://api.slack.com/messaging/webhooks)
    """

    channel_name = "slack"

    def __init__(self, config: dict[str, Any]):
        self.webhook_url = config.get("webhook_url", "")

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, subject: str, body: str, job: dict[str, Any]) -> bool:
        if not self.is_configured():
            logger.warning("SlackChannel: not configured — skipping")
            return False
        if not HAS_REQUESTS:
            logger.warning("SlackChannel: requests not installed — skipping")
            return False
        try:
            # Build a Slack Block Kit message
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": subject},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": body},
                },
            ]
            if job.get("url"):
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Job"},
                            "url": job["url"],
                        }
                    ],
                })

            payload = {"blocks": blocks, "text": subject}
            resp = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Slack notification sent: %s", subject)
            return True
        except Exception as exc:
            logger.error("SlackChannel failed: %s", exc)
            return False
