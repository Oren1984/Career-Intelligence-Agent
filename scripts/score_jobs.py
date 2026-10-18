# scripts/score_jobs.py
# Score all unscored jobs in a workspace against the candidate profile.

"""Score all unscored jobs against the candidate profile.

Usage:
    python scripts/score_jobs.py                    # workspace from $WORKSPACE (default: personal)
    python scripts/score_jobs.py --workspace demo
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse  # noqa: E402
import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from app.db.session import check_db_ready, get_session  # noqa: E402
from app.services.job_service import JobService  # noqa: E402
from app.services.workspace_profile import scoring_profile_for  # noqa: E402
from app.workspace import validate_workspace, workspace_from_env  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Score all unscored jobs.")
    parser.add_argument("--workspace", default=None, help="personal | demo (default: $WORKSPACE or personal)")
    args = parser.parse_args()
    workspace = validate_workspace(args.workspace) if args.workspace else workspace_from_env()

    check_db_ready()
    session = get_session(workspace=workspace)

    try:
        service = JobService(session, profile=scoring_profile_for(workspace))
        count = service.score_all_unscored()
        stats = service.get_summary_stats()

        print(f"
Scoring complete [workspace: {workspace}]:")
        print(f"  Jobs scored      : {count}")
        print(f"  Total jobs in DB : {stats['total_jobs']}")
        print(f"  High matches     : {stats['high_match']}")
        print(f"  Medium matches   : {stats['medium_match']}")
        print(f"  Low matches      : {stats['low_match']}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
