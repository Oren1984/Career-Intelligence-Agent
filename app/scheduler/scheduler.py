# scheduler/scheduler.py
# Part of the Career Intelligence Agent project.
"""
Scheduler module — optional background scheduling for collection and scoring runs.

Uses APScheduler (optional dependency). If APScheduler is not installed,
the module provides graceful stubs and clear error messages.

Install: pip install apscheduler>=3.10.0

Usage:
    from app.scheduler.scheduler import create_scheduler, run_once
    scheduler = create_scheduler(collect_fn, score_fn)
    scheduler.start()
    # ... app runs ...
    scheduler.shutdown()
"""
import logging
from typing import Callable

logger = logging.getLogger(__name__)


def _apscheduler_available() -> bool:
    try:
        import apscheduler  # noqa: F401
        return True
    except ImportError:
        return False


def create_scheduler(
    collect_fn: Callable,
    score_fn: Callable,
    collect_cron: str = "0 */6 * * *",
    score_cron: str = "30 */6 * * *",
):
    """
    Create and return a configured BackgroundScheduler.

    Args:
        collect_fn:   Zero-argument callable that runs job collection.
        score_fn:     Zero-argument callable that runs job scoring.
        collect_cron: Cron expression for collection (default: every 6 hours).
        score_cron:   Cron expression for scoring (default: 30 min after collection).

    Returns:
        APScheduler BackgroundScheduler (not yet started).

    Raises:
        ImportError: If APScheduler is not installed.
    """
    if not _apscheduler_available():
        raise ImportError(
            "APScheduler is not installed. Install it with: pip install apscheduler>=3.10.0"
        )

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        collect_fn,
        CronTrigger.from_crontab(collect_cron, timezone="UTC"),
        id="collect_jobs",
        name="Collect Jobs",
        replace_existing=True,
        misfire_grace_time=300,  # 5 min grace window
    )

    scheduler.add_job(
        score_fn,
        CronTrigger.from_crontab(score_cron, timezone="UTC"),
        id="score_jobs",
        name="Score Jobs",
        replace_existing=True,
        misfire_grace_time=300,
    )

    logger.info(
        "Scheduler configured: collect='%s', score='%s'", collect_cron, score_cron
    )
    return scheduler


def run_once(collect_fn: Callable, score_fn: Callable) -> dict[str, str]:
    """
    Run collection and scoring once immediately (no scheduling).

    Useful for manual runs, Docker init, or testing scheduling logic
    without starting a background thread.

    Returns a dict with 'collect' and 'score' status strings.
    """
    results: dict[str, str] = {}

    logger.info("Running one-shot collection...")
    try:
        collect_fn()
        results["collect"] = "ok"
        logger.info("Collection complete.")
    except Exception as exc:
        results["collect"] = f"error: {exc}"
        logger.error("Collection failed: %s", exc, exc_info=True)

    logger.info("Running one-shot scoring...")
    try:
        score_fn()
        results["score"] = "ok"
        logger.info("Scoring complete.")
    except Exception as exc:
        results["score"] = f"error: {exc}"
        logger.error("Scoring failed: %s", exc, exc_info=True)

    return results


def is_available() -> bool:
    """Return True if APScheduler is installed and scheduling is available."""
    return _apscheduler_available()


def safe_shutdown(scheduler, wait: bool = False) -> None:
    """
    Shut down a BackgroundScheduler only if it is currently running.

    APScheduler raises SchedulerNotRunningError when shutdown() is called on
    a scheduler that was never started. This helper silences that case so
    tests and teardown code do not need to track whether start() was called.

    Args:
        scheduler: A BackgroundScheduler (or any APScheduler scheduler).
        wait:      Passed directly to scheduler.shutdown().
    """
    if not _apscheduler_available():
        return
    try:
        from apscheduler.schedulers.base import STATE_STOPPED
        if scheduler.state != STATE_STOPPED:
            scheduler.shutdown(wait=wait)
        else:
            logger.debug("safe_shutdown: scheduler is already stopped — nothing to do")
    except Exception as exc:
        logger.debug("safe_shutdown: ignoring shutdown error: %s", exc)
