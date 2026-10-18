# tests/test_semantic_scoring.py
# Part of the Career Intelligence Agent project.
"""Tests for V2 semantic scoring and combined scorer."""
from unittest.mock import MagicMock

from app.matching.semantic_scorer import SemanticScorer, SemanticScoreResult, SEMANTIC_THEMES
from app.matching.combined_scorer import CombinedScorer, CombinedScoreResult


def make_job(title: str, description: str):
    """Create a mock job object for scoring tests."""
    job = MagicMock()
    job.title = title
    job.description = description
    return job


# ── SemanticScorer ─────────────────────────────────────────────────────────────

class TestSemanticScorer:
    def test_returns_semantic_score_result(self):
        scorer = SemanticScorer()
        job = make_job("AI Engineer", "We build LLM-based products using Python and Docker.")
        result = scorer.score(job)
        assert isinstance(result, SemanticScoreResult)

    def test_score_range_0_to_10(self):
        scorer = SemanticScorer()
        job = make_job("AI Engineer", "Python, LLM, RAG, Docker, AWS, MLOps, FastAPI")
        result = scorer.score(job)
        assert 0.0 <= result.semantic_score <= 10.0

    def test_high_match_job_scores_high(self):
        scorer = SemanticScorer()
        job = make_job(
            "MLOps Engineer",
            "Python, LLM, RAG, Docker, Kubernetes, AWS, Terraform, MLOps, FastAPI, SQL, "
            "machine learning, AI, embedding, vector database, API, microservice",
        )
        result = scorer.score(job)
        assert result.semantic_score > 5.0

    def test_irrelevant_job_scores_low(self):
        scorer = SemanticScorer()
        job = make_job("Accountant", "Manage spreadsheets and budgets. Excel required.")
        result = scorer.score(job)
        assert result.semantic_score < 3.0

    def test_matched_themes_populated(self):
        scorer = SemanticScorer()
        job = make_job("AI Engineer", "Build LLM and RAG systems with Python.")
        result = scorer.score(job)
        assert len(result.matched_themes) > 0

    def test_missing_themes_populated(self):
        scorer = SemanticScorer()
        job = make_job("Python Dev", "Write Python scripts. No AI/ML involved.")
        result = scorer.score(job)
        # At least some themes should be missing for a pure Python job
        assert isinstance(result.missing_themes, list)

    def test_matched_plus_missing_equals_total_themes(self):
        scorer = SemanticScorer()
        job = make_job("Dev", "some description")
        result = scorer.score(job)
        total = len(result.matched_themes) + len(result.missing_themes)
        assert total == len(scorer.themes)

    def test_theme_hits_dict_populated(self):
        scorer = SemanticScorer()
        job = make_job("LLM Engineer", "Uses LLM and RAG to build agents.")
        result = scorer.score(job)
        assert isinstance(result.theme_hits, dict)
        assert len(result.theme_hits) == len(scorer.themes)

    def test_score_text_method(self):
        scorer = SemanticScorer()
        result = scorer.score_text("AI Engineer", "Python LLM RAG")
        assert isinstance(result, SemanticScoreResult)
        assert 0.0 <= result.semantic_score <= 10.0

    def test_to_dict_has_required_keys(self):
        scorer = SemanticScorer()
        job = make_job("Dev", "Python")
        result = scorer.score(job).to_dict()
        assert "semantic_score" in result
        assert "matched_themes" in result
        assert "missing_themes" in result

    def test_custom_themes(self):
        custom = {"My Theme": ["custom_keyword_xyz"]}
        scorer = SemanticScorer(themes=custom)
        job = make_job("Dev", "has custom_keyword_xyz inside")
        result = scorer.score(job)
        assert "My Theme" in result.matched_themes
        assert result.semantic_score == 10.0  # 1/1 themes matched

    def test_default_themes_defined(self):
        assert len(SEMANTIC_THEMES) >= 4
        for theme_name, keywords in SEMANTIC_THEMES.items():
            assert isinstance(keywords, list)
            assert len(keywords) > 0

    def test_profile_keywords_enrichment(self):
        profile = {"positive_keywords": ["unique_skill_abc_123"]}
        scorer = SemanticScorer(profile=profile)
        job = make_job("Dev", "requires unique_skill_abc_123")
        result = scorer.score(job)
        # The enriched "Profile Skills" theme should be matched
        assert "Profile Skills" in result.matched_themes


# ── CombinedScorer ─────────────────────────────────────────────────────────────

class TestCombinedScorer:
    def test_returns_combined_score_result(self):
        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert isinstance(result, CombinedScoreResult)

    def test_keyword_score_present(self):
        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert isinstance(result.keyword_score, float)

    def test_semantic_score_present(self):
        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert isinstance(result.semantic_score, float)

    def test_final_score_present(self):
        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert isinstance(result.final_score, float)

    def test_final_score_at_least_keyword_score(self):
        """Semantic bonus should only add points (never subtract from keyword score for valid jobs)."""
        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        # final >= keyword because semantic_score >= 0
        assert result.final_score >= result.keyword_score

    def test_rejection_flags_preserved(self):
        scorer = CombinedScorer()
        job = make_job("Senior AI Engineer PhD", "Requires phd and senior experience")
        result = scorer.score(job)
        assert len(result.rejection_flags) > 0

    def test_matched_themes_populated(self):
        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert isinstance(result.matched_themes, list)

    def test_missing_themes_populated(self):
        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert isinstance(result.missing_themes, list)

    def test_explanation_non_empty(self):
        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert len(result.explanation) > 0

    def test_explanation_contains_scores(self):
        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert "Keyword score" in result.explanation or "Final score" in result.explanation

    def test_to_dict_has_v1_compat_keys(self):
        scorer = CombinedScorer()
        job = make_job("Dev", "Python")
        d = scorer.score(job).to_dict()
        assert "match_score" in d
        assert "match_level" in d
        assert "matched_keywords" in d

    def test_to_dict_has_v2_keys(self):
        scorer = CombinedScorer()
        job = make_job("Dev", "Python")
        d = scorer.score(job).to_dict()
        assert "keyword_score" in d
        assert "semantic_score" in d
        assert "final_score" in d
        assert "matched_themes" in d
        assert "missing_themes" in d

    def test_match_score_property_equals_final_score(self):
        scorer = CombinedScorer()
        job = make_job("Dev", "Python")
        result = scorer.score(job)
        assert result.match_score == result.final_score

    def test_final_level_is_valid(self):
        scorer = CombinedScorer()
        job = make_job("Dev", "Python")
        result = scorer.score(job)
        assert result.final_level in {"high", "medium", "low"}

    def test_high_scoring_job_level(self):
        scorer = CombinedScorer()
        job = make_job(
            "AI MLOps Engineer",
            "Python, AI, ML, LLM, RAG, Docker, FastAPI, AWS, Terraform, MLOps, "
            "machine learning, embeddings, vector database",
        )
        result = scorer.score(job)
        assert result.final_level == "high"

    def test_profile_passed_through(self, sample_profile):
        scorer = CombinedScorer(profile=sample_profile)
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert isinstance(result, CombinedScoreResult)
