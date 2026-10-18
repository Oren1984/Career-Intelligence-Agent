# tests/test_analytics.py
# Part of the Career Intelligence Agent project.
"""Tests for V2 analytics — source analytics and improved service stats."""
from app.db.models import Score
from app.db.normalizer import insert_jobs_dedup
from app.collectors.base import RawJob
from app.services.job_service import JobService


def _make_raw_job(title, company, source, description=""):
    return RawJob(
        title=title,
        company=company,
        location="Remote",
        description=description or f"{title} at {company}",
        url=f"http://example.com/{title.replace(' ', '-')}",
        source=source,
    )


class TestSourceAnalytics:
    def test_returns_expected_keys(self, db_session):
        svc = JobService(db_session)
        result = svc.get_source_analytics()
        for key in ["by_source", "by_level", "high_match_ratio", "total_scored", "total_jobs"]:
            assert key in result

    def test_empty_db_returns_zeros(self, db_session):
        svc = JobService(db_session)
        result = svc.get_source_analytics()
        assert result["total_jobs"] == 0
        assert result["total_scored"] == 0
        assert result["high_match_ratio"] == 0.0

    def test_by_source_counts(self, db_session):
        jobs = [
            _make_raw_job("AI Engineer", "Acme", "mock"),
            _make_raw_job("ML Engineer", "Beta", "mock"),
            _make_raw_job("Data Eng", "Corp", "rss"),
        ]
        insert_jobs_dedup(db_session, jobs)

        svc = JobService(db_session)
        result = svc.get_source_analytics()
        assert result["by_source"].get("mock", 0) == 2
        assert result["by_source"].get("rss", 0) == 1

    def test_by_level_after_scoring(self, db_session):
        jobs = [
            _make_raw_job("AI Engineer", "Acme", "mock", "python ai llm rag docker fastapi aws mlops"),
            _make_raw_job("Accountant", "Corp", "rss", "excel spreadsheets finance"),
        ]
        insert_jobs_dedup(db_session, jobs)

        svc = JobService(db_session)
        svc.score_all_unscored()

        result = svc.get_source_analytics()
        total_by_level = sum(result["by_level"].values())
        assert total_by_level == 2

    def test_unscored_count_in_by_level(self, db_session):
        jobs = [_make_raw_job("Engineer", "Corp", "mock")]
        insert_jobs_dedup(db_session, jobs)

        svc = JobService(db_session)
        result = svc.get_source_analytics()
        assert result["by_level"]["unscored"] == 1

    def test_total_jobs_matches(self, db_session):
        jobs = [_make_raw_job(f"Job {i}", "Corp", "mock") for i in range(5)]
        insert_jobs_dedup(db_session, jobs)
        svc = JobService(db_session)
        result = svc.get_source_analytics()
        assert result["total_jobs"] == 5

    def test_high_match_ratio_calculated(self, db_session):
        jobs = [
            _make_raw_job("AI Eng", "Acme", "mock", "python ai llm rag docker fastapi aws mlops machine learning"),
            _make_raw_job("Accountant", "Corp", "rss", "excel finance"),
        ]
        insert_jobs_dedup(db_session, jobs)
        svc = JobService(db_session)
        svc.score_all_unscored()

        result = svc.get_source_analytics()
        # ratio = high_count / total_scored
        assert 0.0 <= result["high_match_ratio"] <= 1.0

    def test_multiple_sources(self, db_session):
        jobs = [
            _make_raw_job("Job A", "Co", "source_alpha"),
            _make_raw_job("Job B", "Co", "source_beta"),
            _make_raw_job("Job C", "Co", "source_alpha"),
        ]
        insert_jobs_dedup(db_session, jobs)
        svc = JobService(db_session)
        result = svc.get_source_analytics()
        assert result["by_source"]["source_alpha"] == 2
        assert result["by_source"]["source_beta"] == 1


class TestV2ScoreFields:
    """Verify that V2 score fields (keyword_score, semantic_score, final_score) are stored."""

    def test_v2_fields_stored_in_score_row(self, db_session):
        jobs = [_make_raw_job("AI Eng", "Acme", "mock", "python ai llm rag docker")]
        insert_jobs_dedup(db_session, jobs)
        svc = JobService(db_session)
        svc.score_all_unscored()

        score = db_session.query(Score).first()
        assert score is not None
        # V2 fields should be set (not None) when CombinedScorer is active
        assert score.semantic_score is not None
        assert score.final_score is not None
        assert score.keyword_score is not None

    def test_v2_fields_in_to_dict(self, db_session):
        jobs = [_make_raw_job("AI Eng", "Acme", "mock", "python ai llm rag docker")]
        insert_jobs_dedup(db_session, jobs)
        svc = JobService(db_session)
        svc.score_all_unscored()

        score = db_session.query(Score).first()
        d = score.to_dict()
        assert "semantic_score" in d
        assert "final_score" in d
        assert "keyword_score" in d
        assert "matched_themes" in d
        assert "missing_themes" in d

    def test_matched_themes_in_score(self, db_session):
        jobs = [_make_raw_job("AI Eng", "Acme", "mock", "python llm rag docker aws")]
        insert_jobs_dedup(db_session, jobs)
        svc = JobService(db_session)
        svc.score_all_unscored()

        score = db_session.query(Score).first()
        themes = score.get_matched_themes()
        assert isinstance(themes, list)

    def test_jobs_with_scores_includes_v2_fields(self, db_session):
        jobs = [_make_raw_job("AI Eng", "Acme", "mock", "python ai llm rag docker")]
        insert_jobs_dedup(db_session, jobs)
        svc = JobService(db_session)
        svc.score_all_unscored()

        results = svc.get_jobs_with_scores()
        assert len(results) == 1
        job = results[0]
        assert "semantic_score" in job
        assert "final_score" in job
        assert "matched_themes" in job


class TestGetSummaryStats:
    """Verify get_summary_stats still works correctly in V2."""

    def test_returns_expected_keys(self, db_session):
        svc = JobService(db_session)
        stats = svc.get_summary_stats()
        for key in ["total_jobs", "high_match", "medium_match", "low_match", "status_counts"]:
            assert key in stats

    def test_correct_counts_after_scoring(self, db_session):
        jobs = [
            _make_raw_job("AI Eng", "Co", "mock", "python ai ml llm rag docker fastapi aws mlops"),
            _make_raw_job("Accountant", "Co", "mock", "excel spreadsheets"),
        ]
        insert_jobs_dedup(db_session, jobs)
        svc = JobService(db_session)
        svc.score_all_unscored()

        stats = svc.get_summary_stats()
        assert stats["total_jobs"] == 2
        # At least one high and one low
        assert stats["high_match"] + stats["medium_match"] + stats["low_match"] == 2
