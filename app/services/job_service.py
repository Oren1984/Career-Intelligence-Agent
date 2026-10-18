# services/job_service.py
# Part of the Career Intelligence Agent project.
"""Orchestration layer — ties collectors, normalization, filtering, and scoring together."""
import json
import logging
from typing import Any

from app.collectors.base import BaseCollector
from app.db.models import Job, Score, StatusHistory, CareerScore, JobFeedback, VALID_FEEDBACK_SIGNALS
from app.db.normalizer import insert_jobs_dedup
from app.filtering.filter_engine import FilterEngine
from app.matching.scorer import Scorer

logger = logging.getLogger(__name__)

VALID_STATUSES = {"new", "reviewing", "saved", "ignored", "applied_manual"}

# V2: combined scoring is opt-in (requires no extra dependencies)
_USE_COMBINED_SCORER = True


def _build_scorer(profile: dict[str, Any] | None):
    """Return CombinedScorer if V2 is enabled, else fall back to Scorer."""
    if _USE_COMBINED_SCORER:
        try:
            from app.matching.combined_scorer import CombinedScorer
            return CombinedScorer(profile=profile)
        except Exception as exc:
            logger.warning("CombinedScorer unavailable, using Scorer: %s", exc)
    return Scorer(profile=profile)


class JobService:
    """High-level service for all job operations."""

    def __init__(self, session, profile: dict[str, Any] | None = None):
        self.session = session
        self.filter_engine = FilterEngine(profile=profile)
        self.scorer = _build_scorer(profile)
        self._profile = profile

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def run_collectors(self, collectors: list[BaseCollector]) -> dict[str, int]:
        """
        Run all given collectors in isolation and persist results.

        Each collector is wrapped in its own try/except so a failure in one
        collector does not prevent others from running.

        Returns stats dict: {collected, inserted, skipped, errors}.
        """
        all_raw = []
        errors = 0

        for collector in collectors:
            logger.info("Running collector: %s", collector.source_name)
            try:
                jobs = collector.collect()
                logger.info(
                    "Collector %s returned %d jobs", collector.source_name, len(jobs)
                )
                all_raw.extend(jobs)
            except Exception as exc:
                errors += 1
                logger.error(
                    "Collector %s failed: %s", collector.source_name, exc, exc_info=True
                )

        try:
            inserted, skipped = insert_jobs_dedup(self.session, all_raw)
        except Exception as exc:
            logger.error("insert_jobs_dedup failed: %s", exc)
            inserted, skipped = 0, 0

        return {
            "collected": len(all_raw),
            "inserted": inserted,
            "skipped": skipped,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score_all_unscored(self) -> int:
        """Score all jobs that don't have a score yet. Returns count scored."""
        try:
            scored_job_ids = {row[0] for row in self.session.query(Score.job_id).all()}
            unscored_jobs = (
                self.session.query(Job).filter(Job.id.notin_(scored_job_ids)).all()
                if scored_job_ids
                else self.session.query(Job).all()
            )
        except Exception as exc:
            logger.error("Failed to query unscored jobs: %s", exc)
            self.session.rollback()
            return 0

        count = 0
        for job in unscored_jobs:
            try:
                result = self.scorer.score(job)
                score_row = self._build_score_row(job.id, result)
                self.session.add(score_row)
                count += 1
            except Exception as exc:
                logger.error("Failed to score job %d: %s", job.id, exc)

        try:
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            logger.error("Commit failed during score_all_unscored: %s", exc)
            return 0

        logger.info("Scored %d jobs", count)
        return count

    def rescore_job(self, job_id: int) -> bool:
        """Re-score a specific job, replacing existing score."""
        try:
            job = self.session.query(Job).filter_by(id=job_id).first()
            if not job:
                return False

            result = self.scorer.score(job)

            existing = self.session.query(Score).filter_by(job_id=job_id).first()
            if existing:
                self.session.delete(existing)

            score_row = self._build_score_row(job.id, result)
            self.session.add(score_row)
            self.session.commit()
            return True
        except Exception as exc:
            self.session.rollback()
            logger.error("Failed to rescore job %d: %s", job_id, exc)
            return False

    def _build_score_row(self, job_id: int, result) -> Score:
        """Build a Score ORM row from a ScoreResult or CombinedScoreResult."""
        # Common V1 fields
        kwargs: dict[str, Any] = dict(
            job_id=job_id,
            match_score=result.match_score,
            match_level=result.match_level,
            matched_keywords=json.dumps(result.matched_keywords),
            missing_keywords=json.dumps(result.missing_keywords),
            rejection_flags=json.dumps(result.rejection_flags),
            explanation=result.explanation,
        )

        # V2 fields — only present on CombinedScoreResult
        if hasattr(result, "keyword_score"):
            kwargs["keyword_score"] = result.keyword_score
        if hasattr(result, "semantic_score"):
            kwargs["semantic_score"] = result.semantic_score
        if hasattr(result, "final_score"):
            kwargs["final_score"] = result.final_score
        if hasattr(result, "matched_themes"):
            kwargs["matched_themes"] = json.dumps(result.matched_themes)
        if hasattr(result, "missing_themes"):
            kwargs["missing_themes"] = json.dumps(result.missing_themes)

        return Score(**kwargs)

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def update_status(self, job_id: int, new_status: str, note: str = "") -> bool:
        """Update job status and record in history."""
        if new_status not in VALID_STATUSES:
            logger.warning("Invalid status: %s", new_status)
            return False

        try:
            job = self.session.query(Job).filter_by(id=job_id).first()
            if not job:
                return False

            old_status = job.status
            job.status = new_status

            history = StatusHistory(
                job_id=job_id,
                old_status=old_status,
                new_status=new_status,
                note=note,
            )
            self.session.add(history)
            self.session.commit()
            logger.info("Job %d status: %s → %s", job_id, old_status, new_status)
            return True
        except Exception as exc:
            self.session.rollback()
            logger.error("Failed to update status for job %d: %s", job_id, exc)
            return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_jobs_with_scores(
        self,
        status_filter: str | None = None,
        match_level_filter: str | None = None,
        text_search: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return jobs joined with their latest score as a list of dicts.
        Supports optional filtering by status, match_level, and text search.
        Returns empty list on any DB error.
        """
        try:
            query = self.session.query(Job)

            if status_filter and status_filter != "all":
                query = query.filter(Job.status == status_filter)

            jobs = query.all()
        except Exception as exc:
            logger.error("Failed to query jobs: %s", exc)
            self.session.rollback()
            return []

        results = []

        for job in jobs:
            try:
                score_row = (
                    self.session.query(Score)
                    .filter_by(job_id=job.id)
                    .order_by(Score.scored_at.desc())
                    .first()
                )

                score_data = score_row.to_dict() if score_row else {
                    "match_score": 0.0,
                    "match_level": "unscored",
                    "matched_keywords": [],
                    "missing_keywords": [],
                    "rejection_flags": [],
                    "explanation": "Not yet scored.",
                    "keyword_score": None,
                    "semantic_score": None,
                    "final_score": None,
                    "matched_themes": [],
                    "missing_themes": [],
                }

                if match_level_filter and match_level_filter != "all":
                    if score_data["match_level"] != match_level_filter:
                        continue

                if text_search:
                    search_lower = text_search.lower()
                    if not (
                        search_lower in job.title.lower()
                        or search_lower in job.company.lower()
                        or search_lower in job.description.lower()
                    ):
                        continue

                record = job.to_dict()
                record.update(score_data)
                results.append(record)
            except Exception as exc:
                logger.error("Error processing job %d: %s", job.id, exc)
                continue

        return results

    def get_summary_stats(self) -> dict[str, Any]:
        """Return summary statistics for the dashboard. Returns safe defaults on error."""
        try:
            total = self.session.query(Job).count()
            high = self.session.query(Score).filter_by(match_level="high").count()
            medium = self.session.query(Score).filter_by(match_level="medium").count()
            low = self.session.query(Score).filter_by(match_level="low").count()

            status_counts: dict[str, int] = {}
            for status in VALID_STATUSES:
                status_counts[status] = self.session.query(Job).filter_by(status=status).count()

            return {
                "total_jobs": total,
                "high_match": high,
                "medium_match": medium,
                "low_match": low,
                "status_counts": status_counts,
            }
        except Exception as exc:
            logger.error("Failed to get summary stats: %s", exc)
            self.session.rollback()
            return {
                "total_jobs": 0,
                "high_match": 0,
                "medium_match": 0,
                "low_match": 0,
                "status_counts": {s: 0 for s in VALID_STATUSES},
            }

    # ------------------------------------------------------------------
    # Career Decision Scoring (V2)
    # ------------------------------------------------------------------

    def career_score_all_unscored(self) -> int:
        """
        Run CareerScorer on all jobs that don't have a CareerScore yet.
        Returns count of jobs scored.
        """
        try:
            from app.matching.career_scorer import CareerScorer
        except ImportError as exc:
            logger.error("CareerScorer not available: %s", exc)
            return 0

        scorer = CareerScorer(profile=self._profile)

        try:
            scored_job_ids = {row[0] for row in self.session.query(CareerScore.job_id).all()}
            unscored = (
                self.session.query(Job).filter(Job.id.notin_(scored_job_ids)).all()
                if scored_job_ids
                else self.session.query(Job).all()
            )
        except Exception as exc:
            logger.error("Failed to query unscored jobs: %s", exc)
            self.session.rollback()
            return 0

        count = 0
        for job in unscored:
            try:
                result = scorer.score(job)
                row = self._build_career_score_row(job.id, result)
                self.session.add(row)
                count += 1
            except Exception as exc:
                logger.error("Failed to career-score job %d: %s", job.id, exc)

        try:
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            logger.error("Commit failed during career_score_all_unscored: %s", exc)
            return 0

        logger.info("Career-scored %d jobs", count)
        return count

    def _build_career_score_row(self, job_id: int, result) -> CareerScore:
        """Build a CareerScore ORM row from a CareerScoreResult."""
        import json
        return CareerScore(
            job_id=job_id,
            overall_fit_score=result.overall_fit_score,
            recommendation_label=result.recommendation_label,
            recommendation_reason=result.recommendation_reason,
            score_breakdown=json.dumps(result.score_breakdown),
            strengths=json.dumps(result.strengths),
            gaps=json.dumps(result.gaps),
            risks=json.dumps(result.risks),
            gap_severity=result.gap_severity,
            easy_to_close_gaps=json.dumps(result.easy_to_close_gaps),
            hard_to_close_gaps=json.dumps(result.hard_to_close_gaps),
            career_direction_alignment=result.career_direction_alignment,
            detected_domain=result.detected_domain,
            detected_seniority=result.detected_seniority,
            detected_work_mode=result.detected_work_mode,
            best_matching_project=result.best_matching_project,
            portfolio_highlights=json.dumps(result.portfolio_highlights),
            action_items=json.dumps(result.action_items),
        )

    def get_jobs_with_career_scores(
        self,
        status_filter: str | None = None,
        label_filter: str | None = None,
        min_fit_score: float | None = None,
        text_search: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return jobs joined with their career scores as a list of dicts.
        Supports filtering by status, recommendation label, fit score, and text.
        """
        try:
            query = self.session.query(Job)
            if status_filter and status_filter != "all":
                query = query.filter(Job.status == status_filter)
            jobs = query.all()
        except Exception as exc:
            logger.error("Failed to query jobs: %s", exc)
            self.session.rollback()
            return []

        results = []
        for job in jobs:
            try:
                career_row = (
                    self.session.query(CareerScore)
                    .filter_by(job_id=job.id)
                    .order_by(CareerScore.scored_at.desc())
                    .first()
                )

                career_data = career_row.to_dict() if career_row else {
                    "overall_fit_score": None,
                    "recommendation_label": "Not Yet Scored",
                    "recommendation_reason": "",
                    "score_breakdown": {},
                    "strengths": [],
                    "gaps": [],
                    "risks": [],
                    "gap_severity": "unknown",
                    "easy_to_close_gaps": [],
                    "hard_to_close_gaps": [],
                    "career_direction_alignment": "unknown",
                    "detected_domain": "",
                    "detected_seniority": "unknown",
                    "detected_work_mode": "unknown",
                    "best_matching_project": "",
                    "portfolio_highlights": [],
                    "action_items": [],
                }

                # Apply filters
                if label_filter and label_filter != "all":
                    if career_data.get("recommendation_label") != label_filter:
                        continue

                if min_fit_score is not None:
                    score = career_data.get("overall_fit_score")
                    if score is None or score < min_fit_score:
                        continue

                if text_search:
                    search_lower = text_search.lower()
                    if not (
                        search_lower in job.title.lower()
                        or search_lower in job.company.lower()
                        or search_lower in job.description.lower()
                    ):
                        continue

                record = job.to_dict()
                record.update(career_data)
                results.append(record)
            except Exception as exc:
                logger.error("Error processing job %d: %s", job.id, exc)
                continue

        # Sort: by fit score desc, then by date desc
        results.sort(
            key=lambda r: (
                r.get("overall_fit_score") or 0,
                r.get("date_found") or "",
            ),
            reverse=True,
        )
        return results

    def get_career_summary_stats(self) -> dict[str, Any]:
        """Return career decision stats for the dashboard."""
        from app.matching.career_scorer import ALL_LABELS
        try:
            total = self.session.query(Job).count()
            scored = self.session.query(CareerScore).count()

            label_counts: dict[str, int] = {}
            for label in ALL_LABELS:
                label_counts[label] = (
                    self.session.query(CareerScore)
                    .filter_by(recommendation_label=label)
                    .count()
                )

            avg_score_row = self.session.query(CareerScore.overall_fit_score).all()
            avg_score = (
                round(sum(r[0] for r in avg_score_row) / len(avg_score_row), 1)
                if avg_score_row else 0.0
            )

            return {
                "total_jobs": total,
                "career_scored": scored,
                "label_counts": label_counts,
                "avg_fit_score": avg_score,
            }
        except Exception as exc:
            logger.error("Failed to get career summary stats: %s", exc)
            self.session.rollback()
            return {
                "total_jobs": 0,
                "career_scored": 0,
                "label_counts": {},
                "avg_fit_score": 0.0,
            }

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def record_feedback(
        self,
        job_id: int,
        signal: str,
        note: str = "",
    ) -> bool:
        """Record a lightweight feedback signal for a job."""
        if signal not in VALID_FEEDBACK_SIGNALS:
            logger.warning("Invalid feedback signal: %s", signal)
            return False
        try:
            fb = JobFeedback(job_id=job_id, feedback_signal=signal, note=note)
            self.session.add(fb)
            self.session.commit()
            logger.info("Feedback recorded: job=%d signal=%s", job_id, signal)
            return True
        except Exception as exc:
            self.session.rollback()
            logger.error("Failed to record feedback for job %d: %s", job_id, exc)
            return False

    def get_feedback_summary(self) -> dict[str, int]:
        """Return count of each feedback signal across all jobs."""
        try:
            rows = self.session.query(
                JobFeedback.feedback_signal,
                __import__("sqlalchemy").func.count(JobFeedback.id),
            ).group_by(JobFeedback.feedback_signal).all()
            return {row[0]: row[1] for row in rows}
        except Exception as exc:
            logger.error("Failed to get feedback summary: %s", exc)
            self.session.rollback()
            return {}

    # ------------------------------------------------------------------
    # Weekly Review
    # ------------------------------------------------------------------

    def generate_weekly_review(self) -> dict[str, Any]:
        """Generate a strategic weekly review from current job data."""
        try:
            from app.matching.weekly_review import WeeklyReviewEngine
        except ImportError as exc:
            logger.error("WeeklyReviewEngine not available: %s", exc)
            return {}

        records = self.get_jobs_with_career_scores()
        engine = WeeklyReviewEngine(profile=self._profile)
        report = engine.generate(records)
        return report.to_dict()

    def get_source_analytics(self) -> dict[str, Any]:
        """
        V2: Return per-source analytics.

        Returns:
            {
                "by_source": {"mock": 15, "rss_weworkremotely": 8, ...},
                "by_level": {"high": 3, "medium": 7, "low": 10, "unscored": 5},
                "high_match_ratio": 0.12,
                "total_scored": 20,
            }
        """
        try:
            jobs = self.session.query(Job).all()

            by_source: dict[str, int] = {}
            for job in jobs:
                src = job.source or "unknown"
                by_source[src] = by_source.get(src, 0) + 1

            scored_ids = {row[0] for row in self.session.query(Score.job_id).all()}
            total_scored = len(scored_ids)
            total = len(jobs)

            high = self.session.query(Score).filter_by(match_level="high").count()
            medium = self.session.query(Score).filter_by(match_level="medium").count()
            low = self.session.query(Score).filter_by(match_level="low").count()
            unscored = total - total_scored

            by_level = {
                "high": high,
                "medium": medium,
                "low": low,
                "unscored": unscored,
            }

            high_match_ratio = round(high / total_scored, 3) if total_scored > 0 else 0.0

            return {
                "by_source": by_source,
                "by_level": by_level,
                "high_match_ratio": high_match_ratio,
                "total_scored": total_scored,
                "total_jobs": total,
            }
        except Exception as exc:
            logger.error("Failed to get source analytics: %s", exc)
            self.session.rollback()
            return {
                "by_source": {},
                "by_level": {"high": 0, "medium": 0, "low": 0, "unscored": 0},
                "high_match_ratio": 0.0,
                "total_scored": 0,
                "total_jobs": 0,
            }
