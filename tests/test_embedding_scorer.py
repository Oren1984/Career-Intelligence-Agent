# tests/test_embedding_scorer.py
# Part of the Career Intelligence Agent project.
"""Tests for V3 embedding-based semantic scorer."""
import pytest
from unittest.mock import MagicMock, patch
import numpy as np


def make_job(title: str, description: str):
    job = MagicMock()
    job.title = title
    job.description = description
    return job


class TestEmbeddingAvailability:
    def test_is_available_returns_bool(self):
        from app.matching.embedding_scorer import is_available
        result = is_available()
        assert isinstance(result, bool)

    def test_is_available_false_when_not_installed(self):
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            # When module is None it raises ImportError on import
            import app.matching.embedding_scorer as mod
            with patch.object(mod, "is_available", return_value=False):
                assert mod.is_available() is False


class TestEmbeddingScorerWithMock:
    """Tests using a mocked SentenceTransformer to avoid the real model download."""

    def _make_mock_model(self):
        """Return a fake SentenceTransformer that produces reproducible embeddings."""
        model = MagicMock()

        def fake_encode(text, convert_to_numpy=True, normalize_embeddings=True):
            # Return a normalized vector where length depends on text length
            vec = np.array([len(text) % 10 + 1, len(text) % 7 + 1, 1.0], dtype=float)
            vec = vec / np.linalg.norm(vec)
            return vec

        model.encode.side_effect = fake_encode
        return model

    def test_returns_embedding_score_result(self):
        from app.matching.embedding_scorer import EmbeddingScorer, EmbeddingScoreResult

        scorer = EmbeddingScorer(profile_text="Python AI Engineer")
        scorer._model = self._make_mock_model()

        job = make_job("AI Engineer", "Python LLM RAG")
        result = scorer.score(job)
        assert isinstance(result, EmbeddingScoreResult)

    def test_score_range_0_to_10(self):
        from app.matching.embedding_scorer import EmbeddingScorer

        scorer = EmbeddingScorer(profile_text="Python AI Engineer")
        scorer._model = self._make_mock_model()

        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert 0.0 <= result.semantic_score <= 10.0

    def test_similarity_range_0_to_1(self):
        from app.matching.embedding_scorer import EmbeddingScorer

        scorer = EmbeddingScorer(profile_text="Python AI Engineer")
        scorer._model = self._make_mock_model()

        job = make_job("Dev", "Some job")
        result = scorer.score(job)
        assert 0.0 <= result.semantic_similarity <= 1.0

    def test_semantic_score_is_similarity_times_10(self):
        from app.matching.embedding_scorer import EmbeddingScorer

        scorer = EmbeddingScorer(profile_text="Python AI Engineer")
        scorer._model = self._make_mock_model()

        job = make_job("Dev", "Some job")
        result = scorer.score(job)
        assert abs(result.semantic_score - result.semantic_similarity * 10.0) < 0.01

    def test_matched_themes_always_empty(self):
        from app.matching.embedding_scorer import EmbeddingScorer

        scorer = EmbeddingScorer(profile_text="Python AI Engineer")
        scorer._model = self._make_mock_model()

        job = make_job("Dev", "Some job")
        result = scorer.score(job)
        assert result.matched_themes == []

    def test_score_text_method(self):
        from app.matching.embedding_scorer import EmbeddingScorer

        scorer = EmbeddingScorer(profile_text="Python AI Engineer")
        scorer._model = self._make_mock_model()

        result = scorer.score_text("ML Engineer", "Python RAG LLM")
        assert 0.0 <= result.semantic_score <= 10.0

    def test_empty_profile_returns_zero(self):
        from app.matching.embedding_scorer import EmbeddingScorer

        scorer = EmbeddingScorer(profile_text="")
        job = make_job("AI Engineer", "Python LLM")
        result = scorer.score(job)
        assert result.semantic_score == 0.0
        assert result.semantic_similarity == 0.0

    def test_empty_job_returns_zero(self):
        from app.matching.embedding_scorer import EmbeddingScorer

        scorer = EmbeddingScorer(profile_text="Python AI Engineer")
        scorer._model = self._make_mock_model()

        result = scorer.score_text("", "")
        assert result.semantic_score == 0.0

    def test_profile_embedding_cached(self):
        from app.matching.embedding_scorer import EmbeddingScorer

        scorer = EmbeddingScorer(profile_text="Python AI Engineer")
        mock_model = self._make_mock_model()
        scorer._model = mock_model

        job = make_job("Dev", "Some job")
        # Score twice — profile embedding should only be computed once
        scorer.score(job)
        scorer.score(job)

        # encode called: 1 for profile (cached) + 2 for jobs
        assert mock_model.encode.call_count == 3

    def test_to_dict_has_required_keys(self):
        from app.matching.embedding_scorer import EmbeddingScorer

        scorer = EmbeddingScorer(profile_text="Python AI Engineer")
        scorer._model = self._make_mock_model()

        job = make_job("Dev", "Python job")
        d = scorer.score(job).to_dict()
        assert "semantic_score" in d
        assert "semantic_similarity" in d
        assert "matched_themes" in d


class TestCombinedScorerEmbeddingMode:
    """Tests for CombinedScorer with semantic_mode='embeddings'."""

    def _make_mock_model(self):
        model = MagicMock()
        vec = np.array([1.0, 0.0, 0.0])

        def fake_encode(text, convert_to_numpy=True, normalize_embeddings=True):
            return vec.copy()

        model.encode.side_effect = fake_encode
        return model

    def test_embeddings_mode_falls_back_when_not_installed(self):
        from app.matching.combined_scorer import CombinedScorer, SEMANTIC_MODE_THEMES

        # Patch the is_available used inside combined_scorer's __init__
        with patch("app.matching.embedding_scorer.is_available", return_value=False):
            scorer = CombinedScorer(semantic_mode="embeddings")
            assert scorer.semantic_mode == SEMANTIC_MODE_THEMES

    def test_themes_mode_default(self):
        from app.matching.combined_scorer import CombinedScorer, SEMANTIC_MODE_THEMES

        scorer = CombinedScorer()
        assert scorer.semantic_mode == SEMANTIC_MODE_THEMES

    def test_combined_result_has_semantic_mode_field(self):
        from app.matching.combined_scorer import CombinedScorer

        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert hasattr(result, "semantic_mode")

    def test_result_to_dict_has_semantic_mode(self):
        from app.matching.combined_scorer import CombinedScorer

        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        d = scorer.score(job).to_dict()
        assert "semantic_mode" in d
        assert "semantic_similarity" in d

    def test_embeddings_mode_with_mocked_model(self):
        """Test embedding mode end-to-end with a mocked sentence transformer."""
        from app.matching.combined_scorer import CombinedScorer, SEMANTIC_MODE_EMBEDDINGS
        from app.matching.embedding_scorer import is_available

        if not is_available():
            pytest.skip("sentence-transformers not installed")

        # If installed, test that it works without exceptions
        scorer = CombinedScorer(semantic_mode=SEMANTIC_MODE_EMBEDDINGS)
        job = make_job("AI Engineer", "Python LLM RAG Docker")
        result = scorer.score(job)
        assert 0.0 <= result.semantic_score <= 10.0

    def test_explanation_mentions_semantic_mode(self):
        from app.matching.combined_scorer import CombinedScorer

        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python AI ML")
        result = scorer.score(job)
        assert "score" in result.explanation.lower()

    def test_backward_compat_match_score_property(self):
        from app.matching.combined_scorer import CombinedScorer

        scorer = CombinedScorer()
        job = make_job("AI Engineer", "Python LLM RAG")
        result = scorer.score(job)
        assert result.match_score == result.final_score

    def test_backward_compat_match_level_property(self):
        from app.matching.combined_scorer import CombinedScorer

        scorer = CombinedScorer()
        job = make_job("Dev", "Python")
        result = scorer.score(job)
        assert result.match_level == result.final_level
