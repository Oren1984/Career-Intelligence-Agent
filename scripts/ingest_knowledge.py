"""
ingest_knowledge.py — Sync local career knowledge files into a workspace's knowledge base.

Usage:
    python scripts/ingest_knowledge.py                      # workspace from $WORKSPACE (default: personal)
    python scripts/ingest_knowledge.py --workspace demo
    python scripts/ingest_knowledge.py --kb-root /path/to/knowledge_base
    python scripts/ingest_knowledge.py --rebuild            # re-chunk and re-embed everything

Documents are chunked, embedded locally (multilingual-e5-small) and stored in
PostgreSQL (pgvector). Re-running is idempotent: unchanged documents are
skipped, edited documents are replaced and deleted documents are removed.
If the embedding model is unavailable, chunks are stored without vectors and
search falls back to TF-IDF.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

# Ensure repo root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync local career knowledge files into PostgreSQL.")
    parser.add_argument("--workspace", default=None, help="personal | demo (default: $WORKSPACE or personal)")
    parser.add_argument("--kb-root", default=None, help="Override the workspace's knowledge base folder")
    parser.add_argument("--rebuild", action="store_true", help="Re-chunk and re-embed every document.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    from app.db.session import check_db_ready  # noqa: PLC0415
    from app.rag.factory import knowledge_service_for  # noqa: PLC0415
    from app.workspace import workspace_from_env, validate_workspace  # noqa: PLC0415

    workspace = validate_workspace(args.workspace) if args.workspace else workspace_from_env()
    check_db_ready()
    ks = knowledge_service_for(workspace, kb_root=args.kb_root)
    logger.info("Workspace: %s | knowledge base root: %s | rebuild: %s", workspace, ks._kb_root, args.rebuild)

    status = ks.ingest(rebuild=args.rebuild)
    report = ks.last_ingest

    print("\n" + "=" * 60)
    print(f"KNOWLEDGE SYNC COMPLETE — workspace '{workspace}'")
    print("=" * 60)
    if report:
        print(f"  Added / updated / unchanged / removed docs: "
              f"{report.added} / {report.updated} / {report.unchanged} / {report.removed}")
    print(f"  Documents:        {status.total_documents}")
    print(f"  Chunks:           {status.total_chunks}")
    print(f"  Embedded chunks:  {status.embedded_chunks} ({status.embedding_model})")
    print(f"  Search backend:   {status.search_backend}")
    if report and report.embedding_error:
        print(f"  Embedding note:   {report.embedding_error}")
    print("=" * 60)
    if not status.is_indexed:
        print(f"\nNo documents indexed. Add .md, .txt, .pdf or .json files to: {ks._kb_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
