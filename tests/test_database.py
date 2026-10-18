# tests/test_database.py
# This file is part of the OpenLLM project issue tracker:

"""Tests for database persistence and integrity."""
from app.db.models import Job, Score, StatusHistory
from app.collectors.base import RawJob
from app.db.normalizer import insert_jobs_dedup
from app.services.job_service import JobService


def _make_raw(title="AI Engineer", company="Corp AI", description="Python docker aws ai"):
    return RawJob(
        title=title,
        company=company,
        location="Remote",
        description=description,
        url="https://example.com/job/test",
        source="test",
        raw_text=description,
    )


class TestJobPersistence:
    def test_job_inserted_and_retrievable(self, db_session):
        raw = _make_raw()
        insert_jobs_dedup(db_session, [raw])
        job = db_session.query(Job).first()
        assert job is not None
        assert job.title == "AI Engineer"
        assert job.company == "Corp AI"
        assert job.status == "new"

    def test_job_has_unique_hash(self, db_session):
        raw = _make_raw()
        insert_jobs_dedup(db_session, [raw])
        job = db_session.query(Job).first()
        assert job.unique_hash
        assert len(job.unique_hash) == 64

    def test_multiple_jobs_stored(self, db_session):
        raws = [_make_raw(f"Job {i}", f"Corp {i}") for i in range(5)]
        insert_jobs_dedup(db_session, raws)
        count = db_session.query(Job).count()
        assert count == 5

    def test_job_to_dict(self, db_session):
        raw = _make_raw()
        insert_jobs_dedup(db_session, [raw])
        job = db_session.query(Job).first()
        d = job.to_dict()
        assert d["title"] == "AI Engineer"
        assert "id" in d
        assert "status" in d


class TestScorePersistence:
    def test_score_stored_and_retrieved(self, db_session, sample_profile):
        raw = _make_raw()
        insert_jobs_dedup(db_session, [raw])
        service = JobService(db_session, profile=sample_profile)
        service.score_all_unscored()

        score = db_session.query(Score).first()
        assert score is not None
        assert score.match_score is not None
        assert score.match_level in ("high", "medium", "low")

    def test_score_keywords_are_lists(self, db_session, sample_profile):
        raw = _make_raw(description="python docker aws ai llm")
        insert_jobs_dedup(db_session, [raw])
        service = JobService(db_session, profile=sample_profile)
        service.score_all_unscored()

        score = db_session.query(Score).first()
        assert isinstance(score.get_matched_keywords(), list)
        assert isinstance(score.get_missing_keywords(), list)
        assert isinstance(score.get_rejection_flags(), list)

    def test_score_explanation_stored(self, db_session, sample_profile):
        raw = _make_raw()
        insert_jobs_dedup(db_session, [raw])
        service = JobService(db_session, profile=sample_profile)
        service.score_all_unscored()

        score = db_session.query(Score).first()
        assert score.explanation
        assert len(score.explanation) > 10


class TestStatusHistory:
    def test_status_update_recorded(self, db_session, sample_profile):
        raw = _make_raw()
        insert_jobs_dedup(db_session, [raw])
        job = db_session.query(Job).first()

        service = JobService(db_session, profile=sample_profile)
        service.update_status(job.id, "reviewing")

        history = db_session.query(StatusHistory).filter_by(job_id=job.id).first()
        assert history is not None
        assert history.old_status == "new"
        assert history.new_status == "reviewing"

    def test_job_status_updated(self, db_session, sample_profile):
        raw = _make_raw()
        insert_jobs_dedup(db_session, [raw])
        job = db_session.query(Job).first()

        service = JobService(db_session, profile=sample_profile)
        service.update_status(job.id, "saved")

        db_session.refresh(job)
        assert job.status == "saved"

    def test_invalid_status_rejected(self, db_session, sample_profile):
        raw = _make_raw()
        insert_jobs_dedup(db_session, [raw])
        job = db_session.query(Job).first()

        service = JobService(db_session, profile=sample_profile)
        result = service.update_status(job.id, "invalid_status")
        assert result is False


class TestJobService:
    def test_get_summary_stats(self, db_session, sample_profile):
        raws = [_make_raw(f"Job {i}", f"Corp {i}") for i in range(3)]
        insert_jobs_dedup(db_session, raws)
        service = JobService(db_session, profile=sample_profile)
        service.score_all_unscored()
        stats = service.get_summary_stats()
        assert stats["total_jobs"] == 3
        assert "high_match" in stats
        assert "medium_match" in stats
        assert "low_match" in stats

    def test_get_jobs_with_scores(self, db_session, sample_profile):
        raw = _make_raw()
        insert_jobs_dedup(db_session, [raw])
        service = JobService(db_session, profile=sample_profile)
        service.score_all_unscored()
        jobs = service.get_jobs_with_scores()
        assert len(jobs) == 1
        assert "match_score" in jobs[0]
        assert "title" in jobs[0]

    def test_run_collectors_returns_stats(self, db_session, sample_profile):
        from app.collectors.mock_collector import MockCollector
        service = JobService(db_session, profile=sample_profile)
        stats = service.run_collectors([MockCollector()])
        assert stats["inserted"] > 0
        assert "skipped" in stats
        assert "collected" in stats


class TestSessionLayer:
    """V2.0 session layer: cached engine/factory, workspace binding."""

    def test_factory_on_fresh_url_does_not_deadlock_and_is_cached(self, tmp_path):
        import threading
        from app.db.session import dispose_engines, get_engine, get_session_factory

        url = f"sqlite:///{tmp_path / 'fresh.db'}"
        result = {}
        t = threading.Thread(target=lambda: result.setdefault("f", get_session_factory(url)), daemon=True)
        t.start()
        t.join(timeout=10)
        assert not t.is_alive(), "get_session_factory deadlocked on a fresh URL"
        assert get_session_factory(url) is result["f"]
        assert result["f"].kw["bind"] is get_engine(url)
        dispose_engines()

    def test_bound_session_stamps_workspace(self, tmp_path):
        from app.db.models import Job
        from app.db.session import check_db_ready, dispose_engines, session_scope

        url = f"sqlite:///{tmp_path / 'ws.db'}"
        check_db_ready(url)
        with session_scope("demo", url) as s:
            s.add(Job(title="t", unique_hash="h" * 64, workspace="personal"))
        with session_scope("demo", url) as s:
            assert s.query(Job).one().workspace == "demo"
        dispose_engines()

    def test_unknown_workspace_rejected(self):
        import pytest
        from app.db.session import bind_workspace
        from app.workspace import WorkspaceError

        with pytest.raises(WorkspaceError):
            bind_workspace(object.__new__(type("S", (), {"info": {}})), "admin'; --")

    def test_missing_database_url_is_explicit(self, monkeypatch):
        import pytest
        from app.db.session import DatabaseNotConfigured, database_url

        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(DatabaseNotConfigured):
            database_url()
