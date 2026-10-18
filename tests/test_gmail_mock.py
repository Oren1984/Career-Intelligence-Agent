# tests/test_gmail_mock.py
# Part of the Career Intelligence Agent project.
"""Tests for the Gmail mock client — does not send real emails."""
from app.integrations.gmail.gmail_mock import GmailMockClient
from app.integrations.gmail.gmail_models import GmailMessage, GmailSendResult
from app.integrations.gmail.gmail_client import GmailClient, ENABLED as GMAIL_ENABLED


def make_message(**kwargs) -> GmailMessage:
    base = {
        "to": "test@example.com",
        "subject": "Test Subject",
        "body": "Test body text.",
    }
    base.update(kwargs)
    return GmailMessage(**base)


# ── GmailMockClient ────────────────────────────────────────────────────────────

class TestGmailMockClient:
    def test_send_returns_success(self):
        client = GmailMockClient()
        result = client.send(make_message())
        assert result.success is True

    def test_send_records_message(self):
        client = GmailMockClient()
        msg = make_message(to="user@test.com", subject="Hello")
        client.send(msg)
        assert len(client.sent_messages) == 1
        assert client.sent_messages[0].to == "user@test.com"

    def test_send_increments_call_count(self):
        client = GmailMockClient()
        client.send(make_message())
        client.send(make_message())
        assert client.call_count == 2

    def test_send_returns_message_id(self):
        client = GmailMockClient()
        result = client.send(make_message())
        assert result.message_id.startswith("mock-msg-")

    def test_force_fail_returns_failure(self):
        client = GmailMockClient(force_fail=True)
        result = client.send(make_message())
        assert result.success is False
        assert result.error

    def test_force_fail_does_not_record_message(self):
        client = GmailMockClient(force_fail=True)
        client.send(make_message())
        assert len(client.sent_messages) == 0

    def test_reset_clears_messages(self):
        client = GmailMockClient()
        client.send(make_message())
        client.send(make_message())
        client.reset()
        assert client.sent_messages == []
        assert client.call_count == 0

    def test_batch_send_multiple_messages(self):
        client = GmailMockClient()
        for i in range(5):
            client.send(make_message(subject=f"Job {i}"))
        assert len(client.sent_messages) == 5

    def test_send_result_is_gmail_send_result(self):
        client = GmailMockClient()
        result = client.send(make_message())
        assert isinstance(result, GmailSendResult)


# ── GmailMessage model ─────────────────────────────────────────────────────────

class TestGmailMessage:
    def test_required_fields(self):
        msg = GmailMessage(to="a@b.com", subject="Sub", body="Body")
        assert msg.to == "a@b.com"
        assert msg.subject == "Sub"
        assert msg.body == "Body"

    def test_default_fields(self):
        msg = GmailMessage(to="a@b.com", subject="Sub", body="Body")
        assert msg.html_body == ""
        assert msg.metadata == {}
        assert msg.from_address == ""


# ── GmailSendResult model ─────────────────────────────────────────────────────

class TestGmailSendResult:
    def test_success_result(self):
        r = GmailSendResult(success=True, message_id="abc123")
        assert r.success is True
        assert r.message_id == "abc123"
        assert r.error == ""

    def test_failure_result(self):
        r = GmailSendResult(success=False, error="Auth failed")
        assert r.success is False
        assert r.error == "Auth failed"


# ── GmailClient disabled behavior ─────────────────────────────────────────────

class TestGmailClientDisabled:
    def test_gmail_enabled_is_false(self):
        """Ensure the real client is NOT activated."""
        assert GMAIL_ENABLED is False

    def test_real_client_send_returns_failure_when_disabled(self):
        client = GmailClient()
        result = client.send(make_message())
        assert result.success is False
        assert "not activated" in result.error.lower() or "disabled" in result.error.lower() or result.error
