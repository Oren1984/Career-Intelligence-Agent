"""
knowledge_service.py — Orchestrates the local knowledge base: ingest → index → retrieve.

This is the main entry point for all RAG operations.

Usage:
    ks = KnowledgeService()
    ks.ingest()           # Load, chunk, and index local documents
    result = ks.retrieve("Docker and Kubernetes experience")
    status = ks.get_status()

Local-only. No network calls. No cloud services.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.rag.document_loader import load_documents
from app.rag.chunker import chunk_documents, DocumentChunk
from app.rag.indexer import build_index, save_index, load_index, LocalIndex
from app.rag.retriever import KnowledgeRetriever, RetrievalResult

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_KB_ROOT = os.path.join(_REPO_ROOT, "knowledge_base")
_DEFAULT_INDEX_DIR = os.path.join(_REPO_ROOT, "data", "knowledge_index")
_META_FILE = os.path.join(_DEFAULT_INDEX_DIR, "metadata.json")


# ── Status model ──────────────────────────────────────────────────────────────

@dataclass
class KnowledgeBaseStatus:
    """Current state of the local knowledge base."""
    is_indexed: bool = False
    total_documents: int = 0
    total_chunks: int = 0
    categories: list[str] = field(default_factory=list)
    kb_root: str = ""
    index_dir: str = ""
    last_ingest_timestamp: Optional[float] = None
    last_ingest_iso: str = ""
    documents_by_category: dict[str, int] = field(default_factory=dict)
    # V2.0 (PostgreSQL-backed workspaces)
    search_backend: str = "tfidf"          # "vector" when embeddings are usable, else "tfidf"
    embedded_chunks: int = 0
    embedding_model: str = ""
    embedding_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_indexed": self.is_indexed,
            "total_documents": self.total_documents,
            "total_chunks": self.total_chunks,
            "categories": self.categories,
            "kb_root": self.kb_root,
            "index_dir": self.index_dir,
            "last_ingest_timestamp": self.last_ingest_timestamp,
            "last_ingest_iso": self.last_ingest_iso,
            "documents_by_category": self.documents_by_category,
            "search_backend": self.search_backend,
            "embedded_chunks": self.embedded_chunks,
            "embedding_model": self.embedding_model,
            "embedding_error": self.embedding_error,
        }


# ── Knowledge Service ─────────────────────────────────────────────────────────

class KnowledgeService:
    """
    Manages the complete lifecycle of the local knowledge base.

    Provides:
    - ingest(): Load documents → chunk → build index → save
    - retrieve(query): Return relevant chunks for a query
    - retrieve_for_job(job_text): Return evidence relevant to a job description
    - get_status(): Current KB status
    - is_ready(): Whether the KB is indexed and ready
    """

    def __init__(
        self,
        kb_root: str | None = None,
        index_dir: str | None = None,
        max_chars: int = 800,
        overlap_chars: int = 80,
        top_k: int = 5,
        min_score: float = 0.01,
    ):
        self._kb_root = kb_root or _DEFAULT_KB_ROOT
        self._index_dir = index_dir or _DEFAULT_INDEX_DIR
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars
        self._top_k = top_k
        self._min_score = min_score

        self._index: Optional[LocalIndex] = None
        self._retriever: Optional[KnowledgeRetriever] = None

        # Try to load existing index at startup
        self._try_load_existing_index()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def ingest(self, rebuild: bool = False) -> KnowledgeBaseStatus:
        """
        Ingest documents from the knowledge base folder.

        Loads all supported files, chunks them, builds a TF-IDF index, and
        saves it to disk.

        Args:
            rebuild: If True, rebuild even if an index already exists.

        Returns:
            KnowledgeBaseStatus with current stats.
        """
        if self._index is not None and not rebuild:
            logger.info("Index already loaded. Use rebuild=True to force re-ingest.")
            return self.get_status()

        logger.info("Starting knowledge base ingestion from: %s", self._kb_root)

        docs = load_documents(self._kb_root)
        if not docs:
            logger.warning(
                "No documents found in %s. "
                "Add .md, .txt, or .pdf files to the knowledge base folder.",
                self._kb_root,
            )
            return self.get_status()

        chunks = chunk_documents(
            docs,
            max_chars=self._max_chars,
            overlap_chars=self._overlap_chars,
        )
        logger.info("Chunked %d documents into %d chunks.", len(docs), len(chunks))

        self._index = build_index(chunks)
        self._retriever = KnowledgeRetriever(self._index, min_score=self._min_score)

        save_index(self._index, self._index_dir)
        self._save_metadata(docs, chunks)

        status = self.get_status()
        logger.info(
            "Ingestion complete: %d docs, %d chunks, %d categories.",
            status.total_documents, status.total_chunks, len(status.categories),
        )
        return status

    def rebuild(self) -> KnowledgeBaseStatus:
        """Force a full rebuild of the index."""
        return self.ingest(rebuild=True)

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        categories: list[str] | None = None,
    ) -> RetrievalResult:
        """
        Retrieve relevant chunks for a free-text query.

        Auto-ingests if no index is loaded and documents are available.
        """
        self._ensure_ready()
        if not self._retriever:
            return RetrievalResult(query=query, kb_size=0)
        return self._retriever.retrieve(
            query,
            top_k=top_k or self._top_k,
            categories=categories,
        )

    def retrieve_for_job(
        self,
        job_description: str,
        top_k: int = 8,
    ) -> RetrievalResult:
        """
        Retrieve evidence relevant to a job description.

        Uses multi-query retrieval for broader coverage.
        """
        self._ensure_ready()
        if not self._retriever:
            return RetrievalResult(query=job_description[:100], kb_size=0)
        return self._retriever.retrieve_for_job(job_description, top_k=top_k)

    # ── Status ────────────────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        """True if an index is loaded and has chunks."""
        return self._index is not None and len(self._index.chunks) > 0

    def get_status(self) -> KnowledgeBaseStatus:
        """Return the current knowledge base status."""
        meta = self._load_metadata()

        if self._index:
            chunks = self._index.chunks
            categories = list({c.category for c in chunks})
            docs_by_cat: dict[str, int] = {}
            doc_ids: set[str] = set()
            for c in chunks:
                doc_ids.add(c.doc_id)
                docs_by_cat[c.category] = docs_by_cat.get(c.category, 0)

            for c in chunks:
                if c.chunk_index == 0:  # Count docs by first chunk
                    docs_by_cat[c.category] = docs_by_cat.get(c.category, 0) + 1

            return KnowledgeBaseStatus(
                is_indexed=True,
                total_documents=meta.get("total_documents", len(doc_ids)),
                total_chunks=len(chunks),
                categories=sorted(categories),
                kb_root=self._kb_root,
                index_dir=self._index_dir,
                last_ingest_timestamp=meta.get("ingest_timestamp"),
                last_ingest_iso=meta.get("ingest_iso", ""),
                documents_by_category=docs_by_cat,
            )

        return KnowledgeBaseStatus(
            is_indexed=False,
            kb_root=self._kb_root,
            index_dir=self._index_dir,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _try_load_existing_index(self) -> None:
        """Try to load an existing index from disk silently."""
        try:
            idx = load_index(self._index_dir)
            if idx and idx.chunks:
                self._index = idx
                self._retriever = KnowledgeRetriever(
                    self._index, min_score=self._min_score
                )
                logger.info(
                    "Loaded existing index: %d chunks.", len(self._index.chunks)
                )
        except Exception as exc:
            logger.debug("Could not load existing index: %s", exc)

    def _ensure_ready(self) -> None:
        """Auto-ingest if not yet indexed and documents exist."""
        if not self._index:
            kb_path = Path(self._kb_root)
            if kb_path.exists() and any(kb_path.rglob("*.md")) or any(kb_path.rglob("*.txt") if kb_path.exists() else []):
                logger.info("No index found; auto-ingesting knowledge base...")
                self.ingest()

    def _save_metadata(self, docs: list, chunks: list) -> None:
        """Save ingestion metadata for status reporting."""
        import time  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415
        os.makedirs(self._index_dir, exist_ok=True)
        ts = time.time()
        meta = {
            "ingest_timestamp": ts,
            "ingest_iso": datetime.fromtimestamp(ts).isoformat(),
            "total_documents": len(docs),
            "total_chunks": len(chunks),
            "categories": list({d.category for d in docs}),
        }
        try:
            with open(_META_FILE, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2)
        except Exception as exc:
            logger.warning("Could not save metadata: %s", exc)

    def _load_metadata(self) -> dict:
        """Load ingestion metadata from disk."""
        try:
            if os.path.exists(_META_FILE):
                with open(_META_FILE, "r", encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            pass
        return {}


# ── Module-level singleton ────────────────────────────────────────────────────
# Shared instance used by the dashboard and job analysis service.
# Lazy-initialized on first access.

_knowledge_service: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    """Return the shared KnowledgeService instance (lazy init)."""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service
