# tests/test_scoring.py
# Part of the Career Intelligence Agent project.
"""Tests for the match scoring engine."""
import pytest
from app.matching.scorer import Scorer, ScoreResult


def _make_job(title="AI Engineer", description="Python Docker AWS LLM RAG MLOps"):
    class FakeJob:
        pass
    job = FakeJob()
    job.title = title
    job.description = description
    return job


class TestScorer:
    @pytest.fixture
    def scorer(self, sample_profile):
        return Scorer(profile=sample_profile)

    def test_returns_score_result(self, scorer):
        job = _make_job()
        result = scorer.score(job)
        assert isinstance(result, ScoreResult)

    def test_high_match_with_many_keywords(self, scorer):
        job = _make_job(description="python ai ml docker fastapi terraform aws llm rag")
        result = scorer.score(job)
        assert result.match_level == "high"
        assert result.match_score >= 8.0

    def test_medium_match_with_some_keywords(self, scorer):
        job = _make_job(description="python docker experience required")
        result = scorer.score(job)
        assert result.match_level in ("medium", "high")
        assert result.match_score >= 4.0

    def test_low_match_with_few_keywords(self, scorer):
        job = _make_job(description="javascript node frontend react")
        result = scorer.score(job)
        assert result.match_level == "low"

    def test_negative_keyword_reduces_score(self, scorer):
        job_clean = _make_job(description="python ai docker llm")
        job_with_neg = _make_job(description="python ai docker llm phd senior")
        result_clean = scorer.score(job_clean)
        result_neg = scorer.score(job_with_neg)
        assert result_neg.match_score < result_clean.match_score

    def test_rejection_flags_populated(self, scorer):
        job = _make_job(description="python ai phd required senior engineer")
        result = scorer.score(job)
        assert len(result.rejection_flags) > 0
        assert any(f in result.rejection_flags for f in ["phd", "senior"])

    def test_matched_keywords_populated(self, scorer):
        job = _make_job(description="python docker aws experience")
        result = scorer.score(job)
        assert "python" in result.matched_keywords
        assert "docker" in result.matched_keywords
        assert "aws" in result.matched_keywords

    def test_missing_keywords_are_complement(self, scorer):
        job = _make_job(description="python only")
        result = scorer.score(job)
        assert "python" in result.matched_keywords
        assert "python" not in result.missing_keywords
        for kw in result.missing_keywords:
            assert kw not in result.matched_keywords

    def test_explanation_is_non_empty_string(self, scorer):
        job = _make_job(description="python ai docker")
        result = scorer.score(job)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 20

    def test_score_to_dict(self, scorer):
        job = _make_job()
        result = scorer.score(job)
        d = result.to_dict()
        assert "match_score" in d
        assert "match_level" in d
        assert "matched_keywords" in d
        assert "explanation" in d

    def test_zero_score_for_no_keywords(self, scorer):
        job = _make_job(title="Operations Manager", description="management leadership budget sales")
        result = scorer.score(job)
        assert result.match_score <= 0

    def test_case_insensitive_scoring(self, scorer):
        job_lower = _make_job(description="python docker aws")
        job_upper = _make_job(description="PYTHON DOCKER AWS")
        r1 = scorer.score(job_lower)
        r2 = scorer.score(job_upper)
        assert r1.match_score == r2.match_score
