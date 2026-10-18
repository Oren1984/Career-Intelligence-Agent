"""
rebuild_index.py — Force a full re-chunk and re-embed of a workspace's knowledge base.

Usage:
    python scripts/rebuild_index.py
    python scripts/rebuild_index.py --workspace demo
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Force rebuild of a workspace's knowledge base.")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--kb-root", default=None)
    args = parser.parse_args()

    from app.db.session import check_db_ready  # noqa: PLC0415
    from app.rag.factory import knowledge_service_for  # noqa: PLC0415
    from app.workspace import workspace_from_env, validate_workspace  # noqa: PLC0415

    workspace = validate_workspace(args.workspace) if args.workspace else workspace_from_env()
    check_db_ready()
    status = knowledge_service_for(workspace, kb_root=args.kb_root).rebuild()
    if status.is_indexed:
        print(f"Index rebuilt [{workspace}]: {status.total_documents} docs, {status.total_chunks} chunks, "
              f"{status.embedded_chunks} embedded ({status.search_backend}).")
    else:
        print("No documents found to index.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
