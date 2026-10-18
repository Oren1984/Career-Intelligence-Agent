# tests/test_filtering.py
# Part of the Career Intelligence Agent project.
"""Tests for the filter engine."""
import pytest
from app.filtering.filter_engine import FilterEngine


def _make_job(title="AI Engineer", description="Python Docker AWS"):
    """Simple mock job object."""
    class FakeJob:
        pass
    job = FakeJob()
    job.title = title
    job.description = description
    return job


class TestFilterEngine:
    @pytest.fixture
    def engine(self, sample_profile):
        return FilterEngine(profile=sample_profile)

    def test_passes_with_positive_keyword(self, engine):
        job = _make_job(description="Experience with python required")
        result = engine.check(job)
        assert result["passes"] is True

    def test_fails_without_positive_keywords(self, engine):
        job = _make_job(title="Operations Manager", description="Management and leadership role with Excel")
        result = engine.check(job)
        assert result["passes"] is False

    def test_fails_with_negative_keyword(self, engine):
        job = _make_job(description="Python AI engineer with PhD preferred")
        result = engine.check(job)
        assert result["passes"] is False

    def test_negative_keyword_in_title_fails(self, engine):
        job = _make_job(title="Senior Python Engineer", description="Python AI docker")
        result = engine.check(job)
        assert result["passes"] is False

    def test_returns_positive_hits(self, engine):
        job = _make_job(description="python and docker experience required")
        result = engine.check(job)
        assert "python" in result["positive_hits"]
        assert "docker" in result["positive_hits"]

    def test_returns_negative_hits(self, engine):
        job = _make_job(description="python senior phd required")
        result = engine.check(job)
        assert "senior" in result["negative_hits"] or "phd" in result["negative_hits"]

    def test_filter_jobs_returns_only_passing(self, engine):
        good = _make_job(description="python ai docker")
        bad = _make_job(title="Operations Manager", description="relocation required, management focus")
        results = engine.filter_jobs([good, bad])
        assert len(results) == 1
        assert results[0] is good

    def test_empty_job_list(self, engine):
        assert engine.filter_jobs([]) == []

    def test_case_insensitive_matching(self, engine):
        job = _make_job(description="PYTHON and DOCKER skills required")
        result = engine.check(job)
        assert result["passes"] is True

    def test_identify_role_category_match(self, engine):
        job = _make_job(title="MLOps Engineer", description="mlops engineer role")
        category = engine.identify_role_category(job)
        assert "mlops" in category.lower() or "engineer" in category.lower()

    def test_identify_role_category_no_match(self, engine):
        job = _make_job(title="Sales Manager", description="sales leadership")
        category = engine.identify_role_category(job)
        assert category == "Other"
