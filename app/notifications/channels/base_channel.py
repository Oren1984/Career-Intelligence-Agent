# notifications/channels/base_channel.py
# Part of the Career Intelligence Agent project.
"""Abstract base class for all notification channels."""
from abc import ABC, abstractmethod
from typing import Any


class BaseChannel(ABC):
    """All notification channels must implement is_configured() and send()."""

    channel_name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this channel has the required config to send messages."""
        ...

    @abstractmethod
    def send(self, subject: str, body: str, job: dict[str, Any]) -> bool:
        """
        Send a notification about a job.

        Args:
            subject: Short subject/title string.
            body:    Full notification message body.
            job:     Job dict (from get_jobs_with_scores).

        Returns:
            True if sent successfully, False otherwise.
        """
        ...
