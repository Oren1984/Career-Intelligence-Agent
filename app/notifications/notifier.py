# notifications/notifier.py
# Part of the Career Intelligence Agent project.
"""
Job notifier — sends alerts when new high-match jobs are discovered.

Supports email, Slack webhook, and Telegram bot channels.
Tracks which jobs have already been notified to prevent duplicate alerts.

Config: config/notifications.yaml
Sent-log: data/notifications_sent.json

Usage (from scheduler or manual script):
    from app.notifications.notifier import Notifier
    n = Notifier()
    sent = n.notify_new_high_matches(session)
    print(f"Notified {sent} new high-match jobs")
"""
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "notifications.yaml"
_DEFAULT_SENT_LOG = Path(__file__).parent.parent.parent / "data" / "notifications_sent.json"

_MESSAGE_TEMPLATE = """\
New High-Match Job Found!

Title:   {title}
Company: {company}
Score:   {score:.1f} ({level})
Source:  {source}
Link:    {url}
"""

_SUBJECT_TEMPLATE = "AI Career Agent: High Match — {title} at {company}"


def _load_config(path: Path | None = None) -> dict[str, Any]:
    """Load notifications.yaml. Returns empty dict if missing."""
    cfg_path = path or _DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return {}
    try:
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning("Could not load notifications config: %s", exc)
        return {}


def _load_sent_log(path: Path | None = None) -> set[int]:
    """Load the set of already-notified job IDs."""
    log_path = path or _DEFAULT_SENT_LOG
    if not log_path.exists():
        return set()
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(int(i) for i in data.get("notified_job_ids", []))
    except Exception as exc:
        logger.warning("Could not read notification log: %s", exc)
        return set()


def _save_sent_log(job_ids: set[int], path: Path | None = None) -> None:
    """Persist the set of notified job IDs to disk."""
    log_path = path or _DEFAULT_SENT_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({"notified_job_ids": sorted(job_ids)}, f, indent=2)
    except Exception as exc:
        logger.error("Could not save notification log: %s", exc)


def _build_channels(config: dict[str, Any]) -> list:
    """Instantiate all enabled and configured channels from config."""
    channels = []

    email_cfg = config.get("email", {})
    if email_cfg.get("enabled", False):
        from app.notifications.channels.email_channel import EmailChannel
        ch = EmailChannel(email_cfg)
        if ch.is_configured():
            channels.append(ch)
        else:
            logger.warning("Email channel enabled but not fully configured — skipping")

    slack_cfg = config.get("slack", {})
    if slack_cfg.get("enabled", False):
        from app.notifications.channels.slack_channel import SlackChannel
        ch = SlackChannel(slack_cfg)
        if ch.is_configured():
            channels.append(ch)
        else:
            logger.warning("Slack channel enabled but not fully configured — skipping")

    telegram_cfg = config.get("telegram", {})
    if telegram_cfg.get("enabled", False):
        from app.notifications.channels.telegram_channel import TelegramChannel
        ch = TelegramChannel(telegram_cfg)
        if ch.is_configured():
            channels.append(ch)
        else:
            logger.warning("Telegram channel enabled but not fully configured — skipping")

    return channels


def _format_message(job: dict[str, Any]) -> tuple[str, str]:
    """Build (subject, body) for a job notification."""
    subject = _SUBJECT_TEMPLATE.format(
        title=job.get("title", "Unknown Title"),
        company=job.get("company", "Unknown Company"),
    )
    body = _MESSAGE_TEMPLATE.format(
        title=job.get("title", "Unknown Title"),
        company=job.get("company", "Unknown Company"),
        score=float(job.get("match_score") or job.get("final_score") or 0.0),
        level=(job.get("match_level") or job.get("final_level") or "unknown").upper(),
        source=job.get("source", "unknown"),
        url=job.get("url", ""),
    )
    return subject, body


class Notifier:
    """
    Sends notifications for new high-match jobs via configured channels.

    Each job is notified at most once (tracked in data/notifications_sent.json).
    """

    def __init__(
        self,
        config_path: Path | None = None,
        sent_log_path: Path | None = None,
    ):
        self.config = _load_config(config_path)
        self._sent_log_path = sent_log_path or _DEFAULT_SENT_LOG
        self.sent_ids = _load_sent_log(self._sent_log_path)
        self.channels = _build_channels(self.config)
        logger.info(
            "Notifier ready: %d channel(s), %d jobs already notified",
            len(self.channels),
            len(self.sent_ids),
        )

    def is_enabled(self) -> bool:
        """Return True if at least one channel is configured and enabled."""
        return len(self.channels) > 0

    def notify_new_high_matches(self, session) -> int:
        """
        Find all high-match jobs not yet notified and send alerts.

        Args:
            session: SQLAlchemy session (used to query jobs with scores).

        Returns:
            Number of notifications successfully sent.
        """
        if not self.channels:
            logger.debug("No channels configured — skipping notifications")
            return 0

        from app.services.job_service import JobService
        svc = JobService(session)
        all_jobs = svc.get_jobs_with_scores(match_level_filter="high")

        new_jobs = [j for j in all_jobs if j.get("id") not in self.sent_ids]
        if not new_jobs:
            logger.info("No new high-match jobs to notify")
            return 0

        logger.info("Found %d new high-match job(s) to notify", len(new_jobs))
        sent_count = 0

        for job in new_jobs:
            job_id = job.get("id")
            subject, body = _format_message(job)
            job_sent = False

            for channel in self.channels:
                try:
                    ok = channel.send(subject=subject, body=body, job=job)
                    if ok:
                        job_sent = True
                        logger.info(
                            "Notified via %s: job %d (%s)", channel.channel_name, job_id, job.get("title")
                        )
                except Exception as exc:
                    logger.error("Channel %s raised: %s", channel.channel_name, exc)

            if job_sent:
                self.sent_ids.add(job_id)
                sent_count += 1

        if sent_count:
            _save_sent_log(self.sent_ids, self._sent_log_path)

        return sent_count

    def notify_job(self, job: dict[str, Any]) -> bool:
        """
        Send a notification for a single job dict.
        Returns True if at least one channel succeeded.
        """
        if not self.channels:
            return False
        subject, body = _format_message(job)
        results = []
        for channel in self.channels:
            try:
                results.append(channel.send(subject=subject, body=body, job=job))
            except Exception as exc:
                logger.error("Channel %s raised: %s", channel.channel_name, exc)
                results.append(False)
        return any(results)
