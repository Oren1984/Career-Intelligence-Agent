# notifications/channels/email_channel.py
# Part of the Career Intelligence Agent project.
"""Email notification channel via SMTP."""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any

from app.notifications.channels.base_channel import BaseChannel

logger = logging.getLogger(__name__)


class EmailChannel(BaseChannel):
    """
    Sends job notifications via SMTP email.

    Config keys (from notifications.yaml under 'email:'):
        smtp_server:   SMTP host (e.g. smtp.gmail.com)
        smtp_port:     Port (default 587 for TLS)
        smtp_user:     Sender email address
        smtp_password: SMTP password or app password
        recipient:     Recipient email address (defaults to smtp_user)
        use_tls:       true/false (default true)
    """

    channel_name = "email"

    def __init__(self, config: dict[str, Any]):
        self.smtp_server = config.get("smtp_server", "")
        self.smtp_port = int(config.get("smtp_port", 587))
        self.smtp_user = config.get("smtp_user", "")
        self.smtp_password = config.get("smtp_password", "")
        self.recipient = config.get("recipient", "") or self.smtp_user
        self.use_tls = config.get("use_tls", True)

    def is_configured(self) -> bool:
        return bool(self.smtp_server and self.smtp_user and self.smtp_password and self.recipient)

    def send(self, subject: str, body: str, job: dict[str, Any]) -> bool:
        if not self.is_configured():
            logger.warning("EmailChannel: not configured — skipping")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_user
            msg["To"] = self.recipient
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=15) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, self.recipient, msg.as_string())

            logger.info("Email sent to %s: %s", self.recipient, subject)
            return True
        except Exception as exc:
            logger.error("EmailChannel failed: %s", exc)
            return False
