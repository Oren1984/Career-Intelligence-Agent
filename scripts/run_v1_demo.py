# scripts/run_v1_demo.py
# This file is part of the OpenLLM project issue tracker:

"""V1 Demo Entrypoint — initialize DB, fetch Israeli source jobs, score, and report.

Usage:
    python scripts/run_v1_demo.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def step_init_db():
    """Initialize (or reset) the database."""
    from app.db.session import check_db_ready

    print("[1/3] Checking database...")
    check_db_ready()
    print("      Database ready.")


def step_fetch_israel():
    """Fetch jobs from Israeli sources (drushim + alljobs, currently mock-safe)."""
    from app.db.session import get_session
    from app.workspace import workspace_from_env
    from app.services.job_service import JobService
    from app.collectors.source_loader import load_collectors

    print("[2/3] Fetching Israeli source jobs (drushim + alljobs)...")

    israel_types = ["drushim", "alljobs", "jobnet", "jobkarov", "jobmaster", "jobify360"]
    collectors = load_collectors(types=israel_types, include_mock=False)

    if not collectors:
        logger.warning("No Israeli collectors loaded — falling back to mock collector")
        from app.collectors.mock_collector import MockCollector
        collectors = [MockCollector()]

    session = get_session(workspace=workspace_from_env())
    try:
        service = JobService(session)
        stats = service.run_collectors(collectors)
        print(f"      Collected: {stats.get('collected', 0)}, "
              f"Inserted: {stats.get('inserted', 0)}, "
              f"Skipped: {stats.get('skipped', 0)} duplicates")
        return stats
    finally:
        session.close()


def step_score():
    """Score all unscored jobs against the candidate profile."""
    from app.db.session import get_session
    from app.workspace import workspace_from_env
    from app.services.job_service import JobService

    print("[3/3] Scoring jobs...")
    session = get_session(workspace=workspace_from_env())
    try:
        service = JobService(session)
        count = service.score_all_unscored()
        summary = service.get_summary_stats()
        print(f"      Scored: {count} jobs")
        return summary
    finally:
        session.close()


def main():
    print()
    print("=" * 60)
    print("  AI Career Agent — V1 Demo")
    print("  Sources: Drushim + AllJobs (mock-safe)")
    print("=" * 60)
    print()

    step_init_db()
    step_fetch_israel()
    summary = step_score()

    print()
    print("=" * 60)
    print("  DEMO READY")
    print(f"  Total jobs in DB : {summary['total_jobs']}")
    print(f"  High matches     : {summary['high_match']}")
    print(f"  Medium matches   : {summary['medium_match']}")
    print(f"  Low matches      : {summary['low_match']}")
    print()
    print("  Dashboard ready. Run:")
    print("    streamlit run dashboard/streamlit_app.py")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
