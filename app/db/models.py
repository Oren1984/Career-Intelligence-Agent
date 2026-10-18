# db/models.py
# this file defines the SQLAlchemy ORM models for the database tables:
# Job, Score, StatusHistory, CareerScore, JobFeedback

"""SQLAlchemy ORM models for the Career Decision Agent database.

Every table is account-owned and carries a ``workspace`` column. On PostgreSQL,
row-level security restricts each transaction to the workspace bound to its
session (see app/db/session.py and app/db/migrations.py).
"""
import json
from sqlalchemy import (
    JSON, Column, Date, Integer, String, Float, Text, DateTime, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector

from app.rag.model_spec import EMBEDDING_DIM
from app.timeutil import utcnow
from app.workspace import DEFAULT_WORKSPACE


class Base(DeclarativeBase):
    pass


class WorkspaceMixin:
    """Adds the workspace column used by row-level security.

    The session layer stamps new rows with the session's bound workspace; the
    default only applies to unbound sessions (unit tests on SQLite). On
    PostgreSQL an unbound session can neither read nor write any row.
    """
    workspace = Column(String(32), nullable=False, default=DEFAULT_WORKSPACE, index=True)


# Note: We use a single "jobs" table to store all collected jobs, regardless of source.
class Job(WorkspaceMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("workspace", "unique_hash", name="uq_jobs_workspace_hash"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), default="")
    location = Column(String(255), default="")
    source = Column(String(100), default="")
    url = Column(String(512), default="")
    description = Column(Text, default="")
    raw_text = Column(Text, default="")
    date_found = Column(DateTime(timezone=True), default=utcnow)
    unique_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(50), default="new")

    scores = relationship("Score", back_populates="job", cascade="all, delete-orphan")
    status_history = relationship("StatusHistory", back_populates="job", cascade="all, delete-orphan")
    career_scores = relationship("CareerScore", back_populates="job", cascade="all, delete-orphan")
    feedback = relationship("JobFeedback", back_populates="job", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "source": self.source,
            "url": self.url,
            "description": self.description,
            "date_found": self.date_found.isoformat() if self.date_found else None,
            "unique_hash": self.unique_hash,
            "status": self.status,
        }


class Score(WorkspaceMixin, Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    match_score = Column(Float, default=0.0)
    match_level = Column(String(20), default="low")
    matched_keywords = Column(Text, default="[]")   # JSON list
    missing_keywords = Column(Text, default="[]")   # JSON list
    rejection_flags = Column(Text, default="[]")    # JSON list
    explanation = Column(Text, default="")
    scored_at = Column(DateTime(timezone=True), default=utcnow)

    # V2 fields — nullable for backward compatibility with existing rows
    keyword_score = Column(Float, nullable=True)     # raw keyword score (before semantic boost)
    semantic_score = Column(Float, nullable=True)    # theme-based semantic score (0–10)
    final_score = Column(Float, nullable=True)       # combined final score
    matched_themes = Column(Text, nullable=True)     # JSON list of matched theme names
    missing_themes = Column(Text, nullable=True)     # JSON list of missing theme names

    job = relationship("Job", back_populates="scores")

    def get_matched_keywords(self) -> list[str]:
        return json.loads(self.matched_keywords or "[]")

    def get_missing_keywords(self) -> list[str]:
        return json.loads(self.missing_keywords or "[]")

    def get_rejection_flags(self) -> list[str]:
        return json.loads(self.rejection_flags or "[]")

    def get_matched_themes(self) -> list[str]:
        return json.loads(self.matched_themes or "[]")

    def get_missing_themes(self) -> list[str]:
        return json.loads(self.missing_themes or "[]")

    def to_dict(self) -> dict:
        effective_score = self.final_score if self.final_score is not None else self.match_score
        return {
            "id": self.id,
            "job_id": self.job_id,
            # V1 compatible
            "match_score": effective_score,
            "match_level": self.match_level,
            "matched_keywords": self.get_matched_keywords(),
            "missing_keywords": self.get_missing_keywords(),
            "rejection_flags": self.get_rejection_flags(),
            "explanation": self.explanation,
            "scored_at": self.scored_at.isoformat() if self.scored_at else None,
            # V2 fields
            "keyword_score": self.keyword_score,
            "semantic_score": self.semantic_score,
            "final_score": self.final_score,
            "matched_themes": self.get_matched_themes(),
            "missing_themes": self.get_missing_themes(),
        }


class StatusHistory(WorkspaceMixin, Base):
    __tablename__ = "status_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    old_status = Column(String(50), default="")
    new_status = Column(String(50), default="")
    changed_at = Column(DateTime(timezone=True), default=utcnow)
    note = Column(Text, default="")

    job = relationship("Job", back_populates="status_history")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
            "note": self.note,
        }


class CareerScore(WorkspaceMixin, Base):
    """
    V2 Career Decision Score — multi-factor scoring with recommendation labels,
    gap analysis, action items, and career direction alignment.

    Stored separately from Score to preserve backward compatibility.
    """
    __tablename__ = "career_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    scored_at = Column(DateTime(timezone=True), default=utcnow)

    # Overall result
    overall_fit_score = Column(Float, default=0.0)          # 0–100
    recommendation_label = Column(String(60), default="")   # Apply Now | Stretch | etc.
    recommendation_reason = Column(Text, default="")

    # Dimension breakdown (JSON dict: dimension → score 0–10)
    score_breakdown = Column(Text, default="{}")

    # Explainability
    strengths = Column(Text, default="[]")                  # JSON list
    gaps = Column(Text, default="[]")                       # JSON list
    risks = Column(Text, default="[]")                      # JSON list

    # Gap analysis
    gap_severity = Column(String(20), default="low")        # low | medium | high
    easy_to_close_gaps = Column(Text, default="[]")         # JSON list
    hard_to_close_gaps = Column(Text, default="[]")         # JSON list

    # Career direction
    career_direction_alignment = Column(String(30), default="unknown")
    detected_domain = Column(String(100), default="")
    detected_seniority = Column(String(30), default="unknown")
    detected_work_mode = Column(String(30), default="unknown")

    # Portfolio
    best_matching_project = Column(String(255), default="")
    portfolio_highlights = Column(Text, default="[]")       # JSON list

    # Action items
    action_items = Column(Text, default="[]")               # JSON list

    job = relationship("Job", back_populates="career_scores")

    # ── JSON helpers ──────────────────────────────────────────────────────────

    def get_score_breakdown(self) -> dict:
        return json.loads(self.score_breakdown or "{}")

    def get_strengths(self) -> list:
        return json.loads(self.strengths or "[]")

    def get_gaps(self) -> list:
        return json.loads(self.gaps or "[]")

    def get_risks(self) -> list:
        return json.loads(self.risks or "[]")

    def get_easy_gaps(self) -> list:
        return json.loads(self.easy_to_close_gaps or "[]")

    def get_hard_gaps(self) -> list:
        return json.loads(self.hard_to_close_gaps or "[]")

    def get_portfolio_highlights(self) -> list:
        return json.loads(self.portfolio_highlights or "[]")

    def get_action_items(self) -> list:
        return json.loads(self.action_items or "[]")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "scored_at": self.scored_at.isoformat() if self.scored_at else None,
            "overall_fit_score": self.overall_fit_score,
            "recommendation_label": self.recommendation_label,
            "recommendation_reason": self.recommendation_reason,
            "score_breakdown": self.get_score_breakdown(),
            "strengths": self.get_strengths(),
            "gaps": self.get_gaps(),
            "risks": self.get_risks(),
            "gap_severity": self.gap_severity,
            "easy_to_close_gaps": self.get_easy_gaps(),
            "hard_to_close_gaps": self.get_hard_gaps(),
            "career_direction_alignment": self.career_direction_alignment,
            "detected_domain": self.detected_domain,
            "detected_seniority": self.detected_seniority,
            "detected_work_mode": self.detected_work_mode,
            "best_matching_project": self.best_matching_project,
            "portfolio_highlights": self.get_portfolio_highlights(),
            "action_items": self.get_action_items(),
        }


class JobFeedback(WorkspaceMixin, Base):
    """
    Lightweight user feedback on job matches.

    Signals: liked, irrelevant, applied, not_interested, too_senior,
             good_fit, wrong_direction.

    Used to slightly influence ranking and recommendations over time.
    """
    __tablename__ = "job_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    feedback_signal = Column(String(50), nullable=False)    # see VALID_FEEDBACK_SIGNALS
    recorded_at = Column(DateTime(timezone=True), default=utcnow)
    note = Column(Text, default="")

    job = relationship("Job", back_populates="feedback")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "feedback_signal": self.feedback_signal,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "note": self.note,
        }


VALID_FEEDBACK_SIGNALS = {
    "liked",
    "irrelevant",
    "applied",
    "not_interested",
    "too_senior",
    "good_fit",
    "wrong_direction",
}


# ── V2.0 tables ───────────────────────────────────────────────────────────────

class KnowledgeChunk(WorkspaceMixin, Base):
    """One retrievable chunk of a knowledge-base document, with its embedding.

    ``doc_hash`` (SHA-256 of the source text) makes re-ingestion idempotent:
    unchanged documents are skipped, changed documents have their chunks
    replaced, and documents removed from disk have their chunks deleted.
    ``embedding_model`` records which model produced ``embedding`` so that a
    model change triggers re-embedding instead of mixing vector spaces.
    """
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("workspace", "chunk_id", name="uq_knowledge_chunks_workspace_chunk"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String(600), nullable=False)        # "{doc_id}::chunk{index}"
    doc_id = Column(String(512), nullable=False, index=True)  # path relative to the workspace KB root
    file_name = Column(String(255), default="")
    category = Column(String(100), default="general")
    chunk_index = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)
    chunk_metadata = Column(JSON, default=dict)
    doc_hash = Column(String(64), nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model = Column(String(160), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Application(WorkspaceMixin, Base):
    """A job application tracked by the user (mirrors Job_Search_Tracker.xlsx).

    Controlled values (status / track / source) are stored as language-neutral
    codes defined in app/tracker/vocab.py. Values that do not map to a code are
    kept verbatim in ``extra["unmapped"]`` and unknown workbook columns in
    ``extra["columns"]``, so imports never silently drop data.
    """
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    row_uid = Column(String(36), nullable=False, unique=True)   # stable identifier (UUID4)
    source_ref = Column(String(64), nullable=True)               # original workbook ID, if any
    submitted_date = Column(Date, nullable=True)
    company = Column(String(255), default="")
    title = Column(String(255), default="")
    track = Column(String(40), nullable=True)
    source = Column(String(40), nullable=True)
    location = Column(String(255), default="")
    salary_range = Column(String(120), default="")
    status = Column(String(40), nullable=True)
    notes = Column(Text, default="")
    closure_reason = Column(Text, default="")
    extra = Column(JSON, default=dict)
    last_update_at = Column(DateTime(timezone=True), default=utcnow)  # drives the 14-day stale rule
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserPreference(WorkspaceMixin, Base):
    """Per-account UI preferences (currently the interface language)."""
    __tablename__ = "user_preferences"

    username = Column(String(64), primary_key=True)
    language = Column(String(8), nullable=False, default="en")
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProfileOverride(WorkspaceMixin, Base):
    """Personal profile overlay (V1 data/personal_profile.json), one row per workspace."""
    __tablename__ = "profile_overrides"
    __table_args__ = (UniqueConstraint("workspace", name="uq_profile_overrides_workspace"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# Tables protected by row-level security (all application tables).
WORKSPACE_TABLES = (
    "jobs", "scores", "status_history", "career_scores", "job_feedback",
    "knowledge_chunks", "applications", "user_preferences", "profile_overrides",
)
