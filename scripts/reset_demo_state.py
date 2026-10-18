# scripts/reset_demo_state.py
# Part of the Career Intelligence Agent project.
"""Reset a workspace's job data — delete its jobs and scores, fetch jobs, score them.

Only the selected workspace's job pipeline rows (jobs, scores, status history,
career scores, feedback) are deleted. Tables are never dropped, and the
knowledge base, tracker and profile are not touched.

Usage:
    python scripts/reset_demo_state.py            # default: israel mode, workspace from $WORKSPACE
    python scripts/reset_demo_state.py --mode mock --workspace demo
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse  # noqa: E402
import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_VALID_MODES = ("mock", "rss", "israel", "all")


def reset_database(workspace: str):
    """Delete the workspace's job pipeline rows (children first)."""
    from app.db.session import check_db_ready, session_scope
    from app.db.models import CareerScore, Job, JobFeedback, Score, StatusHistory

    check_db_ready()
    logger.info("[reset] Deleting job data for workspace '%s'...", workspace)
    with session_scope(workspace) as session:
        for model in (JobFeedback, CareerScore, StatusHistory, Score, Job):
            session.query(model).filter(model.workspace == workspace).delete(synchronize_session=False)
    logger.info("[reset] Workspace job data cleared.")


def fetch_jobs(mode: str, workspace: str):
    """Run the fetch step for the given mode."""
    from app.db.session import get_session
    from app.services.job_service import JobService
    from app.services.workspace_profile import scoring_profile_for
    from scripts.fetch_jobs import build_collectors

    logger.info("[reset] Fetching jobs (mode: %s)...", mode)
    session = get_session(workspace=workspace)
    try:
        collectors = build_collectors(mode)
        if not collectors:
            logger.warning("[reset] No collectors loaded — skipping fetch")
            return {"collected": 0, "inserted": 0, "skipped": 0}
        service = JobService(session, profile=scoring_profile_for(workspace))
        stats = service.run_collectors(collectors)
        logger.info("[reset] Fetch complete: %s", stats)
        return stats
    finally:
        session.close()


def score_jobs(workspace: str):
    """Score all unscored jobs."""
    from app.db.session import get_session
    from app.services.job_service import JobService
    from app.services.workspace_profile import scoring_profile_for

    logger.info("[reset] Scoring all unscored jobs...")
    session = get_session(workspace=workspace)
    try:
        service = JobService(session, profile=scoring_profile_for(workspace))
        count = service.score_all_unscored()
        stats = service.get_summary_stats()
        logger.info("[reset] Scored %d jobs", count)
        return count, stats
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Reset the demo state: drop DB, fetch jobs, score them.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  israel  — Israeli job boards (drushim + alljobs demo data) [default]
  mock    — hardcoded mock jobs
  rss     — RSS feed jobs (requires network)
  all     — all enabled sources

Example:
  python scripts/reset_demo_state.py
  python scripts/reset_demo_state.py --mode mock
        """,
    )
    parser.add_argument(
        "--mode",
        choices=_VALID_MODES,
        default="israel",
        help="Source mode to fetch after reset (default: israel)",
    )
    parser.add_argument("--workspace", default=None, help="personal | demo (default: $WORKSPACE or personal)")
    args = parser.parse_args()

    from app.workspace import validate_workspace, workspace_from_env
    workspace = validate_workspace(args.workspace) if args.workspace else workspace_from_env()

    print()
    print("=" * 60)
    print("  AI Career Agent — Demo State Reset")
    print(f"  Mode: {args.mode.upper()}")
    print("=" * 60)

    # Step 1: Clear this workspace's job data
    print(f"\n[1/3] Clearing job data for workspace '{workspace}'...")
    reset_database(workspace)
    print("      Job data cleared.")

    # Step 2: Fetch jobs
    print(f"\n[2/3] Fetching jobs (mode: {args.mode})...")
    stats = fetch_jobs(args.mode, workspace)
    print(f"      Collected: {stats.get('collected', 0)}, "
          f"Inserted: {stats.get('inserted', 0)}, "
          f"Skipped: {stats.get('skipped', 0)}")

    # Step 3: Score jobs
    print("\n[3/3] Scoring jobs...")
    scored_count, summary = score_jobs(workspace)
    print(f"      Scored: {scored_count} jobs")

    print()
    print("=" * 60)
    print("  RESET COMPLETE")
    print(f"  Total jobs in DB : {summary['total_jobs']}")
    print(f"  High matches     : {summary['high_match']}")
    print(f"  Medium matches   : {summary['medium_match']}")
    print(f"  Low matches      : {summary['low_match']}")
    print()
    print("  Run the dashboard:")
    print("    streamlit run dashboard/streamlit_app.py")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
