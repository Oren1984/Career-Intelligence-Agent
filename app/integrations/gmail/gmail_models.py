# app/integrations/gmail/gmail_models.py
# This file defines data models for the Gmail integration,
# which is planned for future implementation but not yet activated.

"""Data models for Gmail integration — FUTURE / NOT ACTIVATED."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class GmailMessage:
    """Represents a Gmail message to be sent."""
    to: str
    subject: str
    body: str
    from_address: str = ""
    html_body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GmailSendResult:
    """Result of a Gmail send attempt."""
    success: bool
    message_id: str = ""
    error: str = ""
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
