# matching/embedding_scorer.py
# Part of the Career Intelligence Agent project.
"""
Embedding-based semantic scorer using sentence-transformers.

Uses cosine similarity between a candidate profile embedding and a job
description embedding to produce a semantic similarity score (0-10).

Requires: pip install sentence-transformers>=2.7.0

If sentence-transformers is not installed, is_available() returns False
and CombinedScorer automatically falls back to the theme-based scorer.

Embeddings are cached in-memory per scorer instance so that the model
and profile embedding are only computed once per run.
"""
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


def is_available() -> bool:
    """Return True if sentence-transformers is installed."""
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class EmbeddingScoreResult:
    """Result from the embedding-based scorer."""

    semantic_score: float       # 0.0 – 10.0 (similarity * 10)
    semantic_similarity: float  # 0.0 – 1.0  (raw cosine similarity)
    matched_themes: list[str] = field(default_factory=list)  # always empty (not applicable)
    missing_themes: list[str] = field(default_factory=list)  # always empty

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_score": self.semantic_score,
            "semantic_similarity": self.semantic_similarity,
            "matched_themes": self.matched_themes,
            "missing_themes": self.missing_themes,
        }


class EmbeddingScorer:
    """
    Scores a job against a candidate profile using vector embedding cosine similarity.

    The profile embedding is computed once and cached for the lifetime of this
    scorer instance. Job embeddings are computed per call (not cached, as the
    job set changes across runs).

    Args:
        profile_text: The candidate profile as a plain-text string (used to build
                      the profile embedding). If None or empty, scores default to 0.
        model_name:   sentence-transformers model to use.
                      Default: "all-MiniLM-L6-v2" (~80 MB, fast, good quality).
    """

    def __init__(
        self,
        profile_text: str | None = None,
        model_name: str = _DEFAULT_MODEL,
    ):
        self.model_name = model_name
        self._profile_text = (profile_text or "").strip()
        self._model = None
        self._profile_embedding = None

    def _get_model(self):
        """Lazy-load the SentenceTransformer model (cached per instance)."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading sentence-transformer model: %s", self.model_name)
                self._model = SentenceTransformer(self.model_name)
                logger.info("Model loaded.")
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers>=2.7.0"
                ) from exc
        return self._model

    def _get_profile_embedding(self):
        """Compute and cache the profile embedding."""
        if self._profile_embedding is None:
            if not self._profile_text:
                return None
            model = self._get_model()
            self._profile_embedding = model.encode(
                self._profile_text, convert_to_numpy=True, normalize_embeddings=True
            )
        return self._profile_embedding

    def score(self, job) -> EmbeddingScoreResult:
        """Score a Job ORM object using embedding cosine similarity."""
        job_text = f"{job.title} {job.description}".strip()
        return self._score_text(job_text)

    def score_text(self, title: str, description: str) -> EmbeddingScoreResult:
        """Score raw text (for use without a Job ORM object)."""
        job_text = f"{title} {description}".strip()
        return self._score_text(job_text)

    def _score_text(self, job_text: str) -> EmbeddingScoreResult:
        if not job_text or not self._profile_text:
            return EmbeddingScoreResult(semantic_score=0.0, semantic_similarity=0.0)

        try:
            model = self._get_model()
            profile_emb = self._get_profile_embedding()
            if profile_emb is None:
                return EmbeddingScoreResult(semantic_score=0.0, semantic_similarity=0.0)

            import numpy as np
            job_emb = model.encode(
                job_text, convert_to_numpy=True, normalize_embeddings=True
            )

            # Cosine similarity (both embeddings are L2-normalized → dot product = cosine sim)
            similarity = float(np.dot(profile_emb, job_emb))
            similarity = max(0.0, min(1.0, similarity))  # clamp to [0, 1]
            semantic_score = round(similarity * 10.0, 2)

            return EmbeddingScoreResult(
                semantic_score=semantic_score,
                semantic_similarity=round(similarity, 4),
            )
        except Exception as exc:
            logger.error("EmbeddingScorer failed: %s", exc)
            return EmbeddingScoreResult(semantic_score=0.0, semantic_similarity=0.0)
