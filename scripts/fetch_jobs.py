# scripts/fetch_jobs.py
# Part of the Career Intelligence Agent project.
"""Fetch jobs from configured collectors and persist to DB.

Usage:
    python scripts/fetch_jobs.py                # defaults to --mode all
    python scripts/fetch_jobs.py --mode mock
    python scripts/fetch_jobs.py --mode rss
    python scripts/fetch_jobs.py --mode israel
    python scripts/fetch_jobs.py --mode all
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse  # noqa: E402
import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from app.db.session import check_db_ready, get_session  # noqa: E402
from app.services.workspace_profile import scoring_profile_for  # noqa: E402
from app.workspace import validate_workspace, workspace_from_env  # noqa: E402
from app.services.job_service import JobService  # noqa: E402

_VALID_MODES = ("mock", "rss", "israel", "all")


def build_collectors(mode: str) -> list:
    """Build and return the appropriate list of collectors for the given mode."""
    collectors = []

    if mode == "mock":
        logger.info("[fetch] Mode: MOCK — loading MockCollector only")
        from app.collectors.mock_collector import MockCollector
        collectors.append(MockCollector())

    elif mode == "rss":
        logger.info("[fetch] Mode: RSS — loading RSS feeds from sources.yaml")
        from app.collectors.source_loader import load_collectors
        collectors = load_collectors(types=["rss"], include_mock=False)
        if not collectors:
            logger.warning("[fetch] No RSS sources enabled in sources.yaml — falling back to mock")
            from app.collectors.mock_collector import MockCollector
            collectors.append(MockCollector())

    elif mode == "israel":
        logger.info("[fetch] Mode: ISRAELI SOURCES — loading drushim + alljobs")
        from app.collectors.source_loader import load_collectors
        israel_types = ["drushim", "alljobs", "jobnet", "jobkarov", "jobmaster", "jobify360"]
        collectors = load_collectors(types=israel_types, include_mock=False)
        if not collectors:
            logger.warning("[fetch] No Israeli sources enabled in sources.yaml")

    elif mode == "all":
        logger.info("[fetch] Mode: ALL — loading all enabled sources from sources.yaml")
        from app.collectors.source_loader import load_collectors
        collectors = load_collectors(include_mock=True)

    else:
        logger.error("[fetch] Unknown mode: %s (valid: %s)", mode, ", ".join(_VALID_MODES))
        sys.exit(1)

    return collectors


def main():
    parser = argparse.ArgumentParser(
        description="Fetch jobs from configured collectors.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  mock    — hardcoded demo jobs (always works, no network)
  rss     — RSS feeds (weworkremotely, remoteok, etc.)
  israel  — Israeli job boards (drushim, alljobs; currently mock-safe)
  all     — all enabled sources from config/sources.yaml (default)

Examples:
  python scripts/fetch_jobs.py --mode mock
  python scripts/fetch_jobs.py --mode israel
  python scripts/fetch_jobs.py --mode all
        """,
    )
    parser.add_argument(
        "--mode",
        choices=_VALID_MODES,
        default="all",
        help="Source mode to use (default: all)",
    )
    # Legacy flags kept for backward compatibility
    parser.add_argument("--workspace", default=None,
                        help="Workspace to store jobs in: personal | demo (default: $WORKSPACE or personal)")
    parser.add_argument("--mock", action="store_true", default=False,
                        help="[legacy] Alias for --mode mock")
    parser.add_argument("--rss", action="store_true", default=False,
                        help="[legacy] Alias for --mode rss")
    parser.add_argument("--all-sources", action="store_true", default=False,
                        help="[legacy] Alias for --mode all")
    parser.add_argument("--no-mock", action="store_true",
                        help="[legacy] Exclude mock collector")
    args = parser.parse_args()

    # Legacy flag handling — translate to --mode if explicitly set
    if args.mock:
        args.mode = "mock"
    elif args.rss:
        args.mode = "rss"
    elif args.all_sources:
        args.mode = "all"

    logger.info("=" * 60)
    logger.info("AI Career Agent — Job Fetcher")
    logger.info("Mode: %s", args.mode.upper())
    logger.info("=" * 60)

    workspace = validate_workspace(args.workspace) if args.workspace else workspace_from_env()
    logger.info("Workspace: %s", workspace)
    check_db_ready()
    session = get_session(workspace=workspace)

    try:
        collectors = build_collectors(args.mode)

        if not collectors:
            logger.error("[fetch] No collectors could be loaded for mode '%s'", args.mode)
            sys.exit(1)

        logger.info("[fetch] Running %d collector(s)...", len(collectors))

        service = JobService(session, profile=scoring_profile_for(workspace))
        stats = service.run_collectors(collectors)

        print()
        print("=" * 50)
        print(f"  Collection complete  [mode: {args.mode}]")
        print("=" * 50)
        print(f"  Collected : {stats['collected']}")
        print(f"  Inserted  : {stats['inserted']}")
        print(f"  Skipped   : {stats['skipped']} (duplicates)")
        if stats.get("errors", 0) > 0:
            print(f"  Errors    : {stats['errors']} collector(s) failed (see logs)")
        print()

    finally:
        session.close()


if __name__ == "__main__":
    main()
