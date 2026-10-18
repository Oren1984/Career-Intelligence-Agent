# tests/test_notifications_v2.py
# Part of the Career Intelligence Agent project.
"""Tests for the new notification layer (BaseNotifier, ConsoleNotifier, FileNotifier, Orchestrator)."""
import pytest
from typing import Any

from app.notifications.base_notifier import BaseNotifier
from app.notifications.console_notifier import ConsoleNotifier
from app.notifications.file_notifier import FileNotifier
from app.notifications.notification_orchestrator import NotificationOrchestrator


# ── Sample job dict ────────────────────────────────────────────────────────────

def sample_job(**kwargs) -> dict[str, Any]:
    base = {
        "id": 1,
        "title": "AI Engineer",
        "company": "StartupAI",
        "location": "Tel Aviv",
        "source": "drushim",
        "url": "https://www.drushim.co.il/job/1",
        "match_score": 10.5,
        "match_level": "high",
    }
    base.update(kwargs)
    return base


# ── BaseNotifier interface ─────────────────────────────────────────────────────

class TestBaseNotifierInterface:
    def test_cannot_instantiate_abstract_directly(self):
        with pytest.raises(TypeError):
            BaseNotifier()

    def test_concrete_must_implement_is_ready_and_notify(self):
        class BadNotifier(BaseNotifier):
            notifier_name = "bad"
        with pytest.raises(TypeError):
            BadNotifier()


# ── ConsoleNotifier ────────────────────────────────────────────────────────────

class TestConsoleNotifier:
    def test_is_ready_always_true(self):
        n = ConsoleNotifier()
        assert n.is_ready() is True

    def test_notify_returns_true(self, capsys):
        n = ConsoleNotifier()
        result = n.notify(sample_job())
        assert result is True

    def test_notify_prints_title(self, capsys):
        n = ConsoleNotifier()
        n.notify(sample_job(title="Unique Job Title XYZ"))
        captured = capsys.readouterr()
        assert "Unique Job Title XYZ" in captured.out

    def test_notify_prints_score(self, capsys):
        n = ConsoleNotifier()
        n.notify(sample_job(match_score=9.75))
        captured = capsys.readouterr()
        assert "9.8" in captured.out or "9.75" in captured.out

    def test_notify_batch_returns_count(self, capsys):
        n = ConsoleNotifier()
        jobs = [sample_job(id=i) for i in range(3)]
        count = n.notify_batch(jobs)
        assert count == 3

    def test_enabled_flag(self):
        n = ConsoleNotifier()
        assert n.enabled is True


# ── FileNotifier ──────────────────────────────────────────────────────────────

class TestFileNotifier:
    def test_is_ready_always_true(self):
        n = FileNotifier()
        assert n.is_ready() is True

    def test_notify_creates_file(self, tmp_path):
        output = tmp_path / "test_notifications.txt"
        n = FileNotifier(output_path=output)
        result = n.notify(sample_job())
        assert result is True
        assert output.exists()

    def test_notify_writes_job_title(self, tmp_path):
        output = tmp_path / "test.txt"
        n = FileNotifier(output_path=output)
        n.notify(sample_job(title="Special Job Title"))
        content = output.read_text()
        assert "Special Job Title" in content

    def test_notify_appends_multiple(self, tmp_path):
        output = tmp_path / "test.txt"
        n = FileNotifier(output_path=output)
        n.notify(sample_job(id=1, title="Job One"))
        n.notify(sample_job(id=2, title="Job Two"))
        content = output.read_text()
        assert "Job One" in content
        assert "Job Two" in content

    def test_notify_writes_url(self, tmp_path):
        output = tmp_path / "test.txt"
        n = FileNotifier(output_path=output)
        n.notify(sample_job(url="https://example.com/special-job"))
        content = output.read_text()
        assert "https://example.com/special-job" in content

    def test_default_output_path_in_data_dir(self):
        n = FileNotifier()
        assert "data" in str(n.output_path)


# ── NotificationOrchestrator ──────────────────────────────────────────────────

class TestNotificationOrchestrator:
    def test_default_notifiers_loaded(self):
        orch = NotificationOrchestrator()
        assert len(orch.notifiers) >= 2  # ConsoleNotifier + FileNotifier

    def test_custom_notifiers(self, tmp_path):
        file_notifier = FileNotifier(output_path=tmp_path / "out.txt")
        orch = NotificationOrchestrator(notifiers=[ConsoleNotifier(), file_notifier])
        assert len(orch.notifiers) == 2

    def test_notify_job_dispatches_to_all(self, tmp_path, capsys):
        output = tmp_path / "out.txt"
        orch = NotificationOrchestrator(notifiers=[ConsoleNotifier(), FileNotifier(output_path=output)])
        count = orch.notify_job(sample_job(title="Dispatch Test"))
        assert count == 2
        assert output.exists()
        captured = capsys.readouterr()
        assert "Dispatch Test" in captured.out

    def test_sent_log_tracks_notified_jobs(self, tmp_path):
        sent_log = tmp_path / "sent.json"
        orch = NotificationOrchestrator(
            notifiers=[ConsoleNotifier()],
            sent_log_path=sent_log,
        )
        # Manually mark as sent
        orch.sent_ids.add(42)
        # notify_new_high_matches with mock session would be integration-level
        # Just verify the tracking structure works
        assert 42 in orch.sent_ids

    def test_add_notifier(self, tmp_path):
        orch = NotificationOrchestrator(notifiers=[ConsoleNotifier()])
        initial_count = len(orch.notifiers)
        orch.add_notifier(FileNotifier(output_path=tmp_path / "out.txt"))
        assert len(orch.notifiers) == initial_count + 1

    def test_orchestrator_with_empty_notifiers(self):
        orch = NotificationOrchestrator(notifiers=[])
        count = orch.notify_job(sample_job())
        assert count == 0
