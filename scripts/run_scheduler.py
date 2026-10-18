# scripts/run_scheduler.py
# This file is part of the OpenLLM project issue tracker:

"""
Run the background scheduler for automated job collection and scoring.

Usage:
    python scripts/run_scheduler.py [--once] [--collect-cron CRON] [--score-cron CRON]

Options:
    --once           Run collection + scoring once immediately, then exit.
    --collect-cron   Cron expression for collection (default: every 6 hours).
    --score-cron     Cron expression for scoring (default: 30 min after collect).

Examples:
    python scripts/run_scheduler.py --once
    python scripts/run_scheduler.py --collect-cron "0 */4 * * *"

Requirements:
    pip install apscheduler>=3.10.0
"""
import sys
import os
import argparse
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("scheduler")


def _make_collect_fn():
    """Build a zero-argument collect function using the configured sources."""
    from app.db.session import bind_workspace, check_db_ready, get_session_factory
    from app.collectors.source_loader import load_collectors
    from app.services.job_service import JobService
    from app.services.workspace_profile import scoring_profile_for
    from app.workspace import workspace_from_env

    check_db_ready()
    SessionFactory = get_session_factory()
    workspace = workspace_from_env()

    def collect():
        collectors = load_collectors(include_mock=False)
        if not collectors:
            from app.collectors.mock_collector import MockCollector
            collectors = [MockCollector()]
        session = bind_workspace(SessionFactory(), workspace)
        try:
            svc = JobService(session, profile=scoring_profile_for(workspace))
            stats = svc.run_collectors(collectors)
            logger.info(
                "Collection: collected=%d inserted=%d skipped=%d errors=%d",
                stats["collected"], stats["inserted"], stats["skipped"], stats["errors"],
            )
        finally:
            session.close()

    return collect


def _make_score_fn():
    """Build a zero-argument score function."""
    from app.db.session import bind_workspace, check_db_ready, get_session_factory
    from app.services.job_service import JobService
    from app.services.workspace_profile import scoring_profile_for
    from app.workspace import workspace_from_env

    check_db_ready()
    SessionFactory = get_session_factory()
    workspace = workspace_from_env()

    def score():
        session = bind_workspace(SessionFactory(), workspace)
        try:
            svc = JobService(session, profile=scoring_profile_for(workspace))
            n = svc.score_all_unscored()
            logger.info("Scoring: scored %d jobs", n)
        finally:
            session.close()

    return score


def main():
    parser = argparse.ArgumentParser(description="AI Career Agent Scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run collection + scoring once immediately then exit.",
    )
    parser.add_argument(
        "--collect-cron",
        default="0 */6 * * *",
        help="Cron expression for collection runs (default: every 6 hours).",
    )
    parser.add_argument(
        "--score-cron",
        default="30 */6 * * *",
        help="Cron expression for scoring runs (default: 30 min after collection).",
    )
    args = parser.parse_args()

    collect_fn = _make_collect_fn()
    score_fn = _make_score_fn()

    if args.once:
        logger.info("Running one-shot collect + score...")
        from app.scheduler.scheduler import run_once
        results = run_once(collect_fn, score_fn)
        logger.info("Results: %s", results)
        sys.exit(0 if all(v == "ok" for v in results.values()) else 1)

    # Background scheduler
    from app.scheduler.scheduler import create_scheduler, is_available
    if not is_available():
        logger.error(
            "APScheduler not installed. Run: pip install apscheduler>=3.10.0\n"
            "Or use --once for a single run."
        )
        sys.exit(1)

    scheduler = create_scheduler(
        collect_fn=collect_fn,
        score_fn=score_fn,
        collect_cron=args.collect_cron,
        score_cron=args.score_cron,
    )

    logger.info("Starting scheduler (collect='%s', score='%s')", args.collect_cron, args.score_cron)
    logger.info("Press Ctrl+C to stop.")
    scheduler.start()

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown()
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
