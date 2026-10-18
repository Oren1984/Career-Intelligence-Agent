# matching/semantic_scorer.py
# Part of the Career Intelligence Agent project.
"""Semantic matching module — theme-based scoring without external ML dependencies."""
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Semantic themes: groups of related concepts that define profile areas
# Each theme maps to a list of keywords/phrases (case-insensitive substring match)
SEMANTIC_THEMES: dict[str, list[str]] = {
    "AI/ML Engineering": [
        "ai", "ml", "machine learning", "deep learning", "neural network",
        "transformer", "llm", "large language model", "rag", "retrieval",
        "nlp", "natural language", "computer vision", "generative ai",
        "reinforcement learning", "classification", "regression",
    ],
    "LLM Applications": [
        "llm", "rag", "langchain", "openai", "anthropic", "prompt engineering",
        "fine-tuning", "fine tuning", "embedding", "vector database",
        "semantic search", "chatbot", "agent", "tool use", "function calling",
        "multimodal", "gpt", "claude", "gemini",
    ],
    "Python Development": [
        "python", "fastapi", "django", "flask", "asyncio", "pydantic",
        "pytest", "sqlalchemy", "numpy", "pandas", "pytorch", "tensorflow",
        "scikit-learn", "sklearn",
    ],
    "MLOps & Infrastructure": [
        "mlops", "docker", "kubernetes", "k8s", "terraform", "aws",
        "gcp", "azure", "cloud", "ci/cd", "devops", "pipeline", "deployment",
        "monitoring", "observability", "sagemaker", "vertex", "mlflow",
        "airflow", "prefect", "dagster",
    ],
    "Data Engineering": [
        "data pipeline", "spark", "kafka", "airflow", "etl", "dbt",
        "sql", "database", "postgres", "postgresql", "mongodb",
        "data warehouse", "bigquery", "snowflake", "redshift",
    ],
    "API & Backend Development": [
        "api", "rest", "restful", "graphql", "microservice", "backend",
        "server", "endpoint", "grpc", "websocket", "authentication",
    ],
}

# Minimum keyword hits for a theme to be considered "matched"
_THEME_MATCH_THRESHOLD = 1


@dataclass
class SemanticScoreResult:
    semantic_score: float          # 0.0 – 10.0
    matched_themes: list[str] = field(default_factory=list)
    missing_themes: list[str] = field(default_factory=list)
    theme_hits: dict[str, int] = field(default_factory=dict)  # theme → count of keyword hits

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_score": self.semantic_score,
            "matched_themes": self.matched_themes,
            "missing_themes": self.missing_themes,
        }


class SemanticScorer:
    """
    Theme-based semantic scorer.

    Measures how many of the defined semantic themes are represented
    in a job posting. A higher proportion of matched themes yields a
    higher semantic score (0 – 10).

    Works without any API keys or external ML libraries.
    Themes can be customised by passing a custom themes dict.
    """

    def __init__(
        self,
        profile: dict[str, Any] | None = None,
        themes: dict[str, list[str]] | None = None,
    ):
        self.themes = themes or SEMANTIC_THEMES
        # Optionally extend themes with profile skills
        if profile:
            self._enrich_themes_from_profile(profile)

    def _enrich_themes_from_profile(self, profile: dict[str, Any]) -> None:
        """Add any profile positive_keywords not already in themes to a catch-all bucket."""
        all_theme_words: set[str] = set()
        for words in self.themes.values():
            all_theme_words.update(w.lower() for w in words)

        extra = [
            kw.lower()
            for kw in profile.get("positive_keywords", [])
            if kw.lower() not in all_theme_words
        ]
        if extra:
            self.themes = dict(self.themes)  # don't mutate the module-level constant
            self.themes["Profile Skills"] = extra

    def score(self, job) -> SemanticScoreResult:
        """Score a Job ORM object and return a SemanticScoreResult."""
        text = f"{job.title} {job.description}".lower()
        return self._score_text(text)

    def score_text(self, title: str, description: str) -> SemanticScoreResult:
        """Score raw text (for use without a Job ORM object)."""
        text = f"{title} {description}".lower()
        return self._score_text(text)

    def _score_text(self, text: str) -> SemanticScoreResult:
        matched: list[str] = []
        missing: list[str] = []
        theme_hits: dict[str, int] = {}

        for theme_name, keywords in self.themes.items():
            hits = sum(1 for kw in keywords if kw in text)
            theme_hits[theme_name] = hits
            if hits >= _THEME_MATCH_THRESHOLD:
                matched.append(theme_name)
            else:
                missing.append(theme_name)

        total = len(self.themes)
        semantic_score = (len(matched) / total * 10.0) if total > 0 else 0.0

        return SemanticScoreResult(
            semantic_score=round(semantic_score, 2),
            matched_themes=matched,
            missing_themes=missing,
            theme_hits=theme_hits,
        )
