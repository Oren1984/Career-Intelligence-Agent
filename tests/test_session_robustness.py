# tests/test_session_robustness.py
# Part of the Career Intelligence Agent project.
"""Tests for session robustness: rollback handling, recovery after exceptions."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Job
from app.collectors.base import RawJob
from app.db.normalizer import insert_jobs_dedup


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _make_raw(title="AI Engineer", company="Corp", description="Python AI job"):
    return RawJob(
        title=title,
        company=company,
        location="Remote",
        description=description,
        url="https://example.com/job/1",
        source="test",
    )


class TestDuplicateHandling:
    def test_second_batch_skips_all_duplicates(self):
        """Running the same batch twice should insert 0 on the second run."""
        session = _make_session()
        raw_jobs = [_make_raw(f"Job {i}", f"Corp {i}") for i in range(5)]

        inserted1, skipped1 = insert_jobs_dedup(session, raw_jobs)
        assert inserted1 == 5
        assert skipped1 == 0

        inserted2, skipped2 = insert_jobs_dedup(session, raw_jobs)
        assert inserted2 == 0
        assert skipped2 == 5

        session.close()

    def test_within_batch_duplicate_skipped(self):
        """Duplicate within a single batch should be caught in-memory."""
        session = _make_session()
        raw = _make_raw("Same Job", "Same Corp")
        inserted, skipped = insert_jobs_dedup(session, [raw, raw])
        assert inserted == 1
        assert skipped == 1
        session.close()

    def test_db_count_after_duplicates(self):
        """DB record count should equal unique jobs only."""
        session = _make_session()
        batch1 = [_make_raw(f"Job {i}", "Corp") for i in range(3)]
        batch2 = [_make_raw(f"Job {i}", "Corp") for i in range(3)]  # all dupes

        insert_jobs_dedup(session, batch1)
        insert_jobs_dedup(session, batch2)

        count = session.query(Job).count()
        assert count == 3
        session.close()


class TestSessionRecovery:
    def test_session_recovers_after_rollback(self):
        """
        After an explicit rollback the session should still be usable
        for subsequent queries and inserts.
        """
        session = _make_session()

        # Insert one job successfully
        insert_jobs_dedup(session, [_make_raw("Job A", "CorpA")])
        assert session.query(Job).count() == 1

        # Force a rollback to simulate a failed operation
        session.rollback()

        # Session should still be usable
        count = session.query(Job).count()
        assert count == 1

        # Should be able to insert another job
        inserted, skipped = insert_jobs_dedup(session, [_make_raw("Job B", "CorpB")])
        assert inserted == 1
        assert session.query(Job).count() == 2
        session.close()

    def test_insert_after_failed_operation(self):
        """
        insert_jobs_dedup should handle a session that was in a bad state
        (simulated by rollback) without raising.
        """
        session = _make_session()

        # Deliberately break and rollback the session
        try:
            session.execute(__import__("sqlalchemy").text("SELECT * FROM nonexistent_table"))
        except Exception:
            session.rollback()

        # Now insert should work normally
        inserted, skipped = insert_jobs_dedup(session, [_make_raw("Job X", "CorpX")])
        assert inserted == 1
        assert skipped == 0
        session.close()


class TestCollectorIsolation:
    def test_failing_collector_does_not_block_others(self):
        """A collector that raises should not prevent other collectors from running."""
        from app.collectors.base import BaseCollector
        from app.services.job_service import JobService

        class BrokenCollector(BaseCollector):
            source_name = "broken"

            def collect(self):
                raise RuntimeError("Simulated collector failure")

        class GoodCollector(BaseCollector):
            source_name = "good"

            def collect(self):
                return [_make_raw("Good Job", "Good Corp")]

        session = _make_session()
        service = JobService(session)
        stats = service.run_collectors([BrokenCollector(), GoodCollector()])

        assert stats["inserted"] == 1
        assert stats["errors"] == 1
        assert stats["collected"] == 1
        session.close()

    def test_all_collectors_failing_returns_zeros(self):
        """If all collectors fail, stats should reflect zeros cleanly."""
        from app.collectors.base import BaseCollector
        from app.services.job_service import JobService

        class BrokenCollector(BaseCollector):
            source_name = "broken"

            def collect(self):
                raise RuntimeError("failure")

        session = _make_session()
        service = JobService(session)
        stats = service.run_collectors([BrokenCollector()])

        assert stats["inserted"] == 0
        assert stats["collected"] == 0
        assert stats["errors"] == 1
        session.close()
