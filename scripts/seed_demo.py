"""
seed_demo.py — Create the `demo` login and load synthetic data into the demo workspace.

Idempotent: running it again does not duplicate anything.
  1. Creates the `demo` login (password documented in the README) if it does not exist.
  2. Collects the built-in mock jobs into the demo workspace and scores them.
  3. Syncs the synthetic knowledge base (demo/knowledge_base/).
  4. Upserts synthetic job-application rows (demo/tracker_seed.yaml).

Only the demo workspace is written. Usage:
    python scripts/seed_demo.py
    docker compose run --rm tools scripts/seed_demo.py
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo2026"   # public by design: the demo workspace holds synthetic data only


def ensure_demo_user() -> bool:
    from app.auth import load_users, upsert_user  # noqa: PLC0415
    from app.workspace import WORKSPACE_DEMO  # noqa: PLC0415

    if DEMO_USERNAME in load_users():
        return False
    upsert_user(DEMO_USERNAME, WORKSPACE_DEMO, DEMO_PASSWORD)
    return True


def seed_jobs() -> dict:
    from app.collectors.mock_collector import MockCollector  # noqa: PLC0415
    from app.db.session import session_scope  # noqa: PLC0415
    from app.services.job_service import JobService  # noqa: PLC0415
    from app.services.workspace_profile import candidate_profile_for, scoring_profile_for  # noqa: PLC0415
    from app.workspace import WORKSPACE_DEMO  # noqa: PLC0415

    with session_scope(WORKSPACE_DEMO) as session:
        stats = JobService(session, profile=scoring_profile_for(WORKSPACE_DEMO)).run_collectors([MockCollector()])
        stats["classic_scored"] = JobService(session, profile=scoring_profile_for(WORKSPACE_DEMO)).score_all_unscored()
        profile = candidate_profile_for(session, WORKSPACE_DEMO).to_dict()
        stats["career_scored"] = JobService(session, profile=profile).career_score_all_unscored()
    return stats


def seed_knowledge() -> str:
    from app.rag.factory import knowledge_service_for  # noqa: PLC0415
    from app.workspace import WORKSPACE_DEMO  # noqa: PLC0415

    status = knowledge_service_for(WORKSPACE_DEMO).ingest()
    return f"{status.total_documents} docs, {status.total_chunks} chunks, {status.embedded_chunks} embedded ({status.search_backend})"


def seed_tracker() -> int:
    from app.tracker.seed import seed_demo_applications  # noqa: PLC0415

    return seed_demo_applications()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the demo workspace with synthetic data.")
    parser.add_argument("--skip-user", action="store_true", help="Do not create the demo login.")
    args = parser.parse_args()

    from app.db.session import check_db_ready  # noqa: PLC0415

    if not args.skip_user:
        created = ensure_demo_user()
        print(f"Demo login: {'created' if created else 'already exists'} (username '{DEMO_USERNAME}').")
    check_db_ready()
    print(f"Jobs: {seed_jobs()}")
    print(f"Knowledge base: {seed_knowledge()}")
    print(f"Tracker rows upserted: {seed_tracker()}")
    print("Demo workspace ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
