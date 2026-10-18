# tests/test_notifications.py
# Part of the Career Intelligence Agent project.
"""Tests for V3 job notification system."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_high_job(job_id: int = 1) -> dict:
    return {
        "id": job_id,
        "title": "AI Engineer",
        "company": "Acme Corp",
        "match_score": 9.5,
        "final_score": 9.5,
        "match_level": "high",
        "final_level": "high",
        "source": "mock",
        "url": "https://example.com/jobs/1",
    }


# ── Config loading ─────────────────────────────────────────────────────────────

class TestConfigLoading:
    def test_missing_config_returns_empty(self, tmp_path):
        from app.notifications.notifier import _load_config
        result = _load_config(tmp_path / "missing.yaml")
        assert result == {}

    def test_loads_valid_config(self, tmp_path):
        import yaml
        from app.notifications.notifier import _load_config

        cfg = {"email": {"enabled": True, "smtp_server": "smtp.test.com"}}
        cfg_path = tmp_path / "notifications.yaml"
        cfg_path.write_text(yaml.dump(cfg), encoding="utf-8")

        result = _load_config(cfg_path)
        assert result["email"]["smtp_server"] == "smtp.test.com"

    def test_empty_yaml_returns_empty(self, tmp_path):
        from app.notifications.notifier import _load_config

        cfg_path = tmp_path / "notifications.yaml"
        cfg_path.write_text("", encoding="utf-8")
        result = _load_config(cfg_path)
        assert result == {}


# ── Sent log ───────────────────────────────────────────────────────────────────

class TestSentLog:
    def test_missing_log_returns_empty_set(self, tmp_path):
        from app.notifications.notifier import _load_sent_log
        result = _load_sent_log(tmp_path / "missing.json")
        assert result == set()

    def test_saves_and_loads_job_ids(self, tmp_path):
        from app.notifications.notifier import _save_sent_log, _load_sent_log

        log_path = tmp_path / "sent.json"
        _save_sent_log({1, 2, 3}, log_path)
        result = _load_sent_log(log_path)
        assert result == {1, 2, 3}

    def test_saved_log_is_sorted(self, tmp_path):
        from app.notifications.notifier import _save_sent_log

        log_path = tmp_path / "sent.json"
        _save_sent_log({5, 1, 3}, log_path)
        data = json.loads(log_path.read_text())
        assert data["notified_job_ids"] == [1, 3, 5]

    def test_loads_existing_ids(self, tmp_path):
        from app.notifications.notifier import _load_sent_log

        log_path = tmp_path / "sent.json"
        log_path.write_text(json.dumps({"notified_job_ids": [10, 20]}), encoding="utf-8")
        result = _load_sent_log(log_path)
        assert 10 in result and 20 in result


# ── Message formatting ─────────────────────────────────────────────────────────

class TestMessageFormatting:
    def test_subject_contains_title_and_company(self):
        from app.notifications.notifier import _format_message
        job = _make_high_job()
        subject, _ = _format_message(job)
        assert "AI Engineer" in subject
        assert "Acme Corp" in subject

    def test_body_contains_score(self):
        from app.notifications.notifier import _format_message
        job = _make_high_job()
        _, body = _format_message(job)
        assert "9.5" in body

    def test_body_contains_url(self):
        from app.notifications.notifier import _format_message
        job = _make_high_job()
        _, body = _format_message(job)
        assert "example.com" in body

    def test_body_contains_source(self):
        from app.notifications.notifier import _format_message
        job = _make_high_job()
        _, body = _format_message(job)
        assert "mock" in body


# ── Email channel ──────────────────────────────────────────────────────────────

class TestEmailChannel:
    def test_not_configured_without_creds(self):
        from app.notifications.channels.email_channel import EmailChannel
        ch = EmailChannel({})
        assert ch.is_configured() is False

    def test_configured_with_all_fields(self):
        from app.notifications.channels.email_channel import EmailChannel
        ch = EmailChannel({
            "smtp_server": "smtp.test.com",
            "smtp_user": "user@test.com",
            "smtp_password": "secret",
            "recipient": "me@test.com",
        })
        assert ch.is_configured() is True

    def test_send_returns_false_when_not_configured(self):
        from app.notifications.channels.email_channel import EmailChannel
        ch = EmailChannel({})
        result = ch.send("Subject", "Body", _make_high_job())
        assert result is False

    def test_send_calls_smtp(self):
        from app.notifications.channels.email_channel import EmailChannel

        ch = EmailChannel({
            "smtp_server": "smtp.test.com",
            "smtp_port": 587,
            "smtp_user": "user@test.com",
            "smtp_password": "secret",
            "recipient": "me@test.com",
        })

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("app.notifications.channels.email_channel.smtplib.SMTP", return_value=mock_smtp):
            result = ch.send("Test Subject", "Test Body", _make_high_job())

        assert result is True
        mock_smtp.sendmail.assert_called_once()

    def test_send_returns_false_on_smtp_error(self):
        from app.notifications.channels.email_channel import EmailChannel
        import smtplib

        ch = EmailChannel({
            "smtp_server": "smtp.test.com",
            "smtp_user": "u@t.com",
            "smtp_password": "s",
            "recipient": "r@t.com",
        })

        with patch("app.notifications.channels.email_channel.smtplib.SMTP", side_effect=smtplib.SMTPException("fail")):
            result = ch.send("Subject", "Body", _make_high_job())

        assert result is False

    def test_channel_name(self):
        from app.notifications.channels.email_channel import EmailChannel
        assert EmailChannel.channel_name == "email"


# ── Slack channel ──────────────────────────────────────────────────────────────

class TestSlackChannel:
    def test_not_configured_without_webhook(self):
        from app.notifications.channels.slack_channel import SlackChannel
        ch = SlackChannel({})
        assert ch.is_configured() is False

    def test_configured_with_webhook(self):
        from app.notifications.channels.slack_channel import SlackChannel
        ch = SlackChannel({"webhook_url": "https://hooks.slack.com/test"})
        assert ch.is_configured() is True

    def test_send_returns_false_when_not_configured(self):
        from app.notifications.channels.slack_channel import SlackChannel
        ch = SlackChannel({})
        result = ch.send("Subject", "Body", _make_high_job())
        assert result is False

    def test_send_posts_to_webhook(self):
        from app.notifications.channels.slack_channel import SlackChannel

        ch = SlackChannel({"webhook_url": "https://hooks.slack.com/test"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None

        with patch("app.notifications.channels.slack_channel.requests.post", return_value=mock_resp) as mock_post:
            result = ch.send("Test", "Body", _make_high_job())

        assert result is True
        mock_post.assert_called_once()
        assert "hooks.slack.com" in mock_post.call_args[0][0]

    def test_send_returns_false_on_error(self):
        from app.notifications.channels.slack_channel import SlackChannel
        import requests as req

        ch = SlackChannel({"webhook_url": "https://hooks.slack.com/test"})

        with patch("app.notifications.channels.slack_channel.requests.post", side_effect=req.RequestException("err")):
            result = ch.send("Subject", "Body", _make_high_job())

        assert result is False

    def test_channel_name(self):
        from app.notifications.channels.slack_channel import SlackChannel
        assert SlackChannel.channel_name == "slack"


# ── Telegram channel ───────────────────────────────────────────────────────────

class TestTelegramChannel:
    def test_not_configured_without_token(self):
        from app.notifications.channels.telegram_channel import TelegramChannel
        ch = TelegramChannel({})
        assert ch.is_configured() is False

    def test_configured_with_token_and_chat(self):
        from app.notifications.channels.telegram_channel import TelegramChannel
        ch = TelegramChannel({"bot_token": "TOKEN", "chat_id": "123"})
        assert ch.is_configured() is True

    def test_send_returns_false_when_not_configured(self):
        from app.notifications.channels.telegram_channel import TelegramChannel
        ch = TelegramChannel({})
        result = ch.send("Subject", "Body", _make_high_job())
        assert result is False

    def test_send_posts_to_api(self):
        from app.notifications.channels.telegram_channel import TelegramChannel

        ch = TelegramChannel({"bot_token": "TOKEN123", "chat_id": "456"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None

        with patch("app.notifications.channels.telegram_channel.requests.post", return_value=mock_resp) as mock_post:
            result = ch.send("Subject", "Body", _make_high_job())

        assert result is True
        assert "TOKEN123" in mock_post.call_args[0][0]

    def test_send_returns_false_on_error(self):
        from app.notifications.channels.telegram_channel import TelegramChannel
        import requests as req

        ch = TelegramChannel({"bot_token": "TOKEN", "chat_id": "123"})

        with patch("app.notifications.channels.telegram_channel.requests.post",
                   side_effect=req.RequestException("err")):
            result = ch.send("Subject", "Body", _make_high_job())

        assert result is False

    def test_channel_name(self):
        from app.notifications.channels.telegram_channel import TelegramChannel
        assert TelegramChannel.channel_name == "telegram"


# ── Notifier orchestrator ──────────────────────────────────────────────────────

class TestNotifier:
    def _make_notifier(self, tmp_path: Path, config: dict | None = None, sent_ids: set | None = None):
        """Create a Notifier instance with controlled config and sent log."""
        from app.notifications.notifier import Notifier, _save_sent_log
        import yaml

        cfg_path = tmp_path / "notifications.yaml"
        cfg = config or {}
        cfg_path.write_text(yaml.dump(cfg), encoding="utf-8")

        sent_log = tmp_path / "sent.json"
        if sent_ids is not None:
            _save_sent_log(sent_ids, sent_log)

        return Notifier(config_path=cfg_path, sent_log_path=sent_log)

    def test_is_enabled_false_with_no_channels(self, tmp_path):
        n = self._make_notifier(tmp_path)
        assert n.is_enabled() is False

    def test_notify_returns_zero_with_no_channels(self, tmp_path, db_session):
        n = self._make_notifier(tmp_path)
        result = n.notify_new_high_matches(db_session)
        assert result == 0

    def test_does_not_notify_already_sent_job(self, tmp_path, db_session):
        high_job = _make_high_job(job_id=42)

        mock_svc = MagicMock()
        mock_svc.get_jobs_with_scores.return_value = [high_job]

        n = self._make_notifier(
            tmp_path,
            config={"slack": {"enabled": True, "webhook_url": "https://hooks.slack.com/x"}},
            sent_ids={42},  # already notified
        )

        with patch("app.services.job_service.JobService", return_value=mock_svc):
            result = n.notify_new_high_matches(db_session)

        assert result == 0

    def test_notifies_new_high_job(self, tmp_path, db_session):
        high_job = _make_high_job(job_id=99)

        mock_svc = MagicMock()
        mock_svc.get_jobs_with_scores.return_value = [high_job]

        mock_channel = MagicMock()
        mock_channel.send.return_value = True

        n = self._make_notifier(tmp_path)
        n.channels = [mock_channel]

        with patch("app.services.job_service.JobService", return_value=mock_svc):
            result = n.notify_new_high_matches(db_session)

        assert result == 1
        mock_channel.send.assert_called_once()

    def test_saves_sent_ids_after_notify(self, tmp_path, db_session):
        from app.notifications.notifier import _load_sent_log

        high_job = _make_high_job(job_id=77)

        mock_svc = MagicMock()
        mock_svc.get_jobs_with_scores.return_value = [high_job]

        mock_channel = MagicMock()
        mock_channel.send.return_value = True

        sent_log = tmp_path / "sent.json"
        n = self._make_notifier(tmp_path)
        n.channels = [mock_channel]
        n._sent_log_path = sent_log

        with patch("app.services.job_service.JobService", return_value=mock_svc):
            n.notify_new_high_matches(db_session)

        saved = _load_sent_log(sent_log)
        assert 77 in saved

    def test_notify_job_single(self, tmp_path):
        n = self._make_notifier(tmp_path)

        mock_channel = MagicMock()
        mock_channel.send.return_value = True
        n.channels = [mock_channel]

        result = n.notify_job(_make_high_job())
        assert result is True
        mock_channel.send.assert_called_once()

    def test_notify_job_returns_false_no_channels(self, tmp_path):
        n = self._make_notifier(tmp_path)
        result = n.notify_job(_make_high_job())
        assert result is False

    def test_notify_job_partial_failure(self, tmp_path):
        """If one channel fails and another succeeds, returns True."""
        n = self._make_notifier(tmp_path)

        good = MagicMock()
        good.send.return_value = True
        bad = MagicMock()
        bad.send.return_value = False

        n.channels = [bad, good]
        result = n.notify_job(_make_high_job())
        assert result is True

    def test_no_duplicate_notifications(self, tmp_path, db_session):
        """Sending the same job twice should only notify once."""
        high_job = _make_high_job(job_id=55)

        mock_svc = MagicMock()
        mock_svc.get_jobs_with_scores.return_value = [high_job]

        mock_channel = MagicMock()
        mock_channel.send.return_value = True

        sent_log = tmp_path / "sent.json"
        n = self._make_notifier(tmp_path)
        n.channels = [mock_channel]
        n._sent_log_path = sent_log

        with patch("app.services.job_service.JobService", return_value=mock_svc):
            n.notify_new_high_matches(db_session)
            n.notify_new_high_matches(db_session)

        # Channel should only be called once (second run skips already-notified job)
        assert mock_channel.send.call_count == 1
