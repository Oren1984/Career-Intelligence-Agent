# notifications/channels/telegram_channel.py
# Part of the Career Intelligence Agent project.
"""Telegram bot notification channel."""
import logging
from typing import Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from app.notifications.channels.base_channel import BaseChannel

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramChannel(BaseChannel):
    """
    Sends job notifications via a Telegram bot.

    Setup:
        1. Create a bot via @BotFather → get bot_token
        2. Start a chat with your bot → get chat_id via
           https://api.telegram.org/bot{token}/getUpdates

    Config keys (from notifications.yaml under 'telegram:'):
        bot_token: Telegram bot token from @BotFather
        chat_id:   Target chat ID (user or group)
    """

    channel_name = "telegram"

    def __init__(self, config: dict[str, Any]):
        self.bot_token = config.get("bot_token", "")
        self.chat_id = str(config.get("chat_id", ""))

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, subject: str, body: str, job: dict[str, Any]) -> bool:
        if not self.is_configured():
            logger.warning("TelegramChannel: not configured — skipping")
            return False
        if not HAS_REQUESTS:
            logger.warning("TelegramChannel: requests not installed — skipping")
            return False
        try:
            # Telegram uses MarkdownV2 — escape special chars
            text = f"*{_escape(subject)}*\n\n{_escape(body)}"
            if job.get("url"):
                text += f"\n\n[View Job]({job['url']})"

            url = _API_URL.format(token=self.bot_token)
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": False,
            }
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Telegram notification sent: %s", subject)
            return True
        except Exception as exc:
            logger.error("TelegramChannel failed: %s", exc)
            return False


def _escape(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))
