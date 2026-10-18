# matching/combined_scorer.py
# Part of the Career Intelligence Agent project.
"""Combined scoring — merges keyword rules with semantic matching.

Supports two semantic modes:
  "themes"     — theme-based keyword matching (default, no dependencies)
  "embeddings" — sentence-transformer cosine similarity (requires sentence-transformers)

If "embeddings" is requested but sentence-transformers is not installed,
the scorer silently falls back to "themes" and logs a warning.
"""
import logging
from dataclasses import dataclass, field
from typing import Any

from app.matching.scorer import Scorer, _determine_level
from app.matching.semantic_scorer import SemanticScorer

logger = logging.getLogger(__name__)

# Weight of semantic score bonus (0-10 scale → adds up to SEMANTIC_MAX_BONUS points)
_SEMANTIC_MAX_BONUS = 2.0
_HIGH_THRESHOLD = 8.0
_MEDIUM_THRESHOLD = 4.0

SEMANTIC_MODE_THEMES = "themes"
SEMANTIC_MODE_EMBEDDINGS = "embeddings"


@dataclass
class CombinedScoreResult:
    """Full V2/V3 score result combining keyword rules and semantic matching."""

    # V2+ fields
    keyword_score: float
    semantic_score: float
    final_score: float
    final_level: str
    matched_themes: list[str] = field(default_factory=list)
    missing_themes: list[str] = field(default_factory=list)

    # V3 embedding field (None when using theme mode)
    semantic_similarity: float | None = None
    semantic_mode: str = SEMANTIC_MODE_THEMES

    # V1-compatible fields (preserved for backward compatibility)
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    rejection_flags: list[str] = field(default_factory=list)
    explanation: str = ""

    # Aliases for backward compatibility
    @property
    def match_score(self) -> float:
        return self.final_score

    @property
    def match_level(self) -> str:
        return self.final_level

    def to_dict(self) -> dict[str, Any]:
        return {
            # V2+
            "keyword_score": self.keyword_score,
            "semantic_score": self.semantic_score,
            "final_score": self.final_score,
            "final_level": self.final_level,
            "matched_themes": self.matched_themes,
            "missing_themes": self.missing_themes,
            # V3
            "semantic_similarity": self.semantic_similarity,
            "semantic_mode": self.semantic_mode,
            # V1 compatible
            "match_score": self.final_score,
            "match_level": self.final_level,
            "matched_keywords": self.matched_keywords,
            "missing_keywords": self.missing_keywords,
            "rejection_flags": self.rejection_flags,
            "explanation": self.explanation,
        }


def _build_combined_explanation(
    keyword_score: float,
    semantic_score: float,
    final_score: float,
    final_level: str,
    matched_themes: list[str],
    missing_themes: list[str],
    matched_keywords: list[str],
    rejection_flags: list[str],
    semantic_mode: str = SEMANTIC_MODE_THEMES,
    semantic_similarity: float | None = None,
) -> str:
    parts = [f"Final score: {final_score:.1f} ({final_level.upper()})."]

    if semantic_mode == SEMANTIC_MODE_EMBEDDINGS and semantic_similarity is not None:
        parts.append(
            f"Keyword score: {keyword_score:.1f} | "
            f"Embedding similarity: {semantic_similarity:.2f} → semantic score {semantic_score:.1f}/10."
        )
    else:
        parts.append(
            f"Keyword score: {keyword_score:.1f} | Semantic score: {semantic_score:.1f}/10."
        )

    if matched_keywords:
        parts.append(f"Matched skills: {', '.join(matched_keywords)}.")

    if matched_themes:
        parts.append(f"Aligned themes: {', '.join(matched_themes)}.")

    if missing_themes:
        parts.append(f"Themes not covered: {', '.join(missing_themes[:3])}.")

    if rejection_flags:
        parts.append(
            f"Rejection flags: {', '.join(rejection_flags)}. "
            "This role may not fit your target seniority or location preferences."
        )

    if final_level == "high":
        parts.append("Strong match — this role closely aligns with your profile.")
    elif final_level == "medium":
        parts.append("Moderate match — worth reviewing further.")
    else:
        parts.append("Low match — likely outside your current target profile.")

    return " ".join(parts)


class CombinedScorer:
    """
    Combines rules-based keyword scoring with semantic matching.

    Supports two semantic modes via the semantic_mode parameter:

    - "themes" (default): theme-based keyword matching (no dependencies required)
    - "embeddings": sentence-transformer cosine similarity
      Requires: pip install sentence-transformers>=2.7.0
      Falls back to "themes" automatically if not installed.

    Final score formula (same for both modes):
        final_score = keyword_score + (semantic_score / 10) * SEMANTIC_MAX_BONUS
    """

    def __init__(
        self,
        profile: dict[str, Any] | None = None,
        keyword_scores: dict[str, float] | None = None,
        semantic_mode: str = SEMANTIC_MODE_THEMES,
        candidate_profile=None,   # CandidateProfile instance for embedding mode
    ):
        self.keyword_scorer = Scorer(profile=profile, keyword_scores=keyword_scores)

        resolved_mode = semantic_mode
        if semantic_mode == SEMANTIC_MODE_EMBEDDINGS:
            from app.matching.embedding_scorer import is_available as emb_available
            if emb_available():
                try:
                    from app.matching.embedding_scorer import EmbeddingScorer
                    profile_text = (
                        candidate_profile.to_prompt_string()
                        if candidate_profile is not None
                        else ""
                    )
                    self.semantic_scorer = EmbeddingScorer(profile_text=profile_text)
                    resolved_mode = SEMANTIC_MODE_EMBEDDINGS
                    logger.info("CombinedScorer: using embedding mode")
                except Exception as exc:
                    logger.warning("Failed to initialise EmbeddingScorer: %s — falling back to themes", exc)
                    self.semantic_scorer = SemanticScorer(profile=profile)
                    resolved_mode = SEMANTIC_MODE_THEMES
            else:
                logger.warning(
                    "sentence-transformers not installed — falling back to theme-based semantic scoring. "
                    "Install with: pip install sentence-transformers>=2.7.0"
                )
                self.semantic_scorer = SemanticScorer(profile=profile)
                resolved_mode = SEMANTIC_MODE_THEMES
        else:
            self.semantic_scorer = SemanticScorer(profile=profile)

        self.semantic_mode = resolved_mode

    def score(self, job) -> CombinedScoreResult:
        """Score a Job ORM object and return a CombinedScoreResult."""
        kw = self.keyword_scorer.score(job)
        sem = self.semantic_scorer.score(job)

        semantic_bonus = (sem.semantic_score / 10.0) * _SEMANTIC_MAX_BONUS
        final_score = round(kw.match_score + semantic_bonus, 2)
        final_level = _determine_level(final_score)

        # Embedding-specific field
        semantic_similarity = getattr(sem, "semantic_similarity", None)

        explanation = _build_combined_explanation(
            keyword_score=kw.match_score,
            semantic_score=sem.semantic_score,
            final_score=final_score,
            final_level=final_level,
            matched_themes=getattr(sem, "matched_themes", []),
            missing_themes=getattr(sem, "missing_themes", []),
            matched_keywords=kw.matched_keywords,
            rejection_flags=kw.rejection_flags,
            semantic_mode=self.semantic_mode,
            semantic_similarity=semantic_similarity,
        )

        return CombinedScoreResult(
            keyword_score=kw.match_score,
            semantic_score=sem.semantic_score,
            final_score=final_score,
            final_level=final_level,
            matched_themes=getattr(sem, "matched_themes", []),
            missing_themes=getattr(sem, "missing_themes", []),
            semantic_similarity=semantic_similarity,
            semantic_mode=self.semantic_mode,
            matched_keywords=kw.matched_keywords,
            missing_keywords=kw.missing_keywords,
            rejection_flags=kw.rejection_flags,
            explanation=explanation,
        )
