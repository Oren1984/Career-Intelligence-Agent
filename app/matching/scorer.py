# matching/scorer.py
# Part of the Career Intelligence Agent project.
"""Match scoring engine — rules-based scoring against the candidate profile."""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_PROFILE_PATH = Path(__file__).parent.parent.parent / "config" / "profile.yaml"

# Default keyword scoring weights
_DEFAULT_KEYWORD_SCORES: dict[str, float] = {
    "python": 2.0,
    "ai": 3.0,
    "ml": 3.0,
    "docker": 2.0,
    "fastapi": 2.0,
    "terraform": 2.0,
    "aws": 2.0,
    "llm": 3.0,
    "rag": 3.0,
    "mlops": 3.0,
    # Negative weights
    "senior": -2.0,
    "phd": -3.0,
    "principal": -3.0,
    "relocation": -2.0,
    "10+ years": -2.0,
    "10+ year": -2.0,
}

_HIGH_THRESHOLD = 8.0
_MEDIUM_THRESHOLD = 4.0


@dataclass
class ScoreResult:
    match_score: float
    match_level: str   # "high" | "medium" | "low"
    matched_keywords: list[str]
    missing_keywords: list[str]
    rejection_flags: list[str]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_score": self.match_score,
            "match_level": self.match_level,
            "matched_keywords": self.matched_keywords,
            "missing_keywords": self.missing_keywords,
            "rejection_flags": self.rejection_flags,
            "explanation": self.explanation,
        }


def _load_profile(profile_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(profile_path or _DEFAULT_PROFILE_PATH)
    if not path.exists():
        return {"positive_keywords": [], "negative_keywords": []}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _determine_level(score: float) -> str:
    if score >= _HIGH_THRESHOLD:
        return "high"
    if score >= _MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _build_explanation(
    score: float,
    level: str,
    matched: list[str],
    missing: list[str],
    rejection_flags: list[str],
) -> str:
    parts = [f"Match score: {score:.1f} ({level.upper()})."]

    if matched:
        parts.append(f"Matched skills: {', '.join(matched)}.")
    else:
        parts.append("No profile keywords matched.")

    if missing:
        parts.append(f"Missing from profile: {', '.join(missing)}.")

    if rejection_flags:
        parts.append(
            f"Rejection flags detected: {', '.join(rejection_flags)}. "
            "This job may not be a good fit due to seniority or relocation requirements."
        )

    if level == "high":
        parts.append("Strong candidate — this role aligns well with your profile.")
    elif level == "medium":
        parts.append("Moderate match — worth reviewing further.")
    else:
        parts.append("Low match — likely outside your current target profile.")

    return " ".join(parts)


class Scorer:
    """
    Scores a job against the candidate profile using keyword-based rules.

    Each positive keyword found adds to the score.
    Each negative keyword found subtracts from the score.
    """

    def __init__(
        self,
        profile: dict[str, Any] | None = None,
        keyword_scores: dict[str, float] | None = None,
    ):
        if profile is None:
            profile = _load_profile()
        self.positive_keywords: list[str] = [k.lower() for k in profile.get("positive_keywords", [])]
        self.negative_keywords: list[str] = [k.lower() for k in profile.get("negative_keywords", [])]
        self.keyword_scores = {
            k.lower(): v for k, v in (keyword_scores or _DEFAULT_KEYWORD_SCORES).items()
        }

    def score(self, job) -> ScoreResult:
        """Score a Job ORM object and return a ScoreResult."""
        text = f"{job.title} {job.description}".lower()

        total_score = 0.0
        matched: list[str] = []
        rejection_flags: list[str] = []

        # Score positive keywords
        for kw in self.positive_keywords:
            if kw in text:
                points = self.keyword_scores.get(kw, 1.0)
                total_score += points
                matched.append(kw)

        # Score negative keywords (subtract)
        for kw in self.negative_keywords:
            if kw in text:
                penalty = abs(self.keyword_scores.get(kw, 2.0))
                total_score -= penalty
                rejection_flags.append(kw)

        # Missing = positive keywords NOT found
        missing = [kw for kw in self.positive_keywords if kw not in matched]

        level = _determine_level(total_score)
        explanation = _build_explanation(total_score, level, matched, missing, rejection_flags)

        return ScoreResult(
            match_score=round(total_score, 2),
            match_level=level,
            matched_keywords=matched,
            missing_keywords=missing,
            rejection_flags=rejection_flags,
            explanation=explanation,
        )
