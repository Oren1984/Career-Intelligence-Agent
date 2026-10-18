"""
workspace_knowledge.py — PostgreSQL-backed knowledge base for one workspace.

Same public interface as KnowledgeService (ingest / rebuild / retrieve /
retrieve_for_job / is_ready / get_status), so RAGJobAnalyzer and
CareerQAService work unchanged.

Storage: chunks live in the ``knowledge_chunks`` table, scoped by workspace
(explicit filter here + row-level security in the database).

Search:
1. Vector search (pgvector, cosine distance over multilingual-e5-small
   embeddings) when the model loads and chunks are embedded with it.
2. TF-IDF fallback otherwise (or on any vector error), built in memory from
   the same workspace's chunks — no on-disk index that could go stale.

Ingestion is a sync, not an append: unchanged documents are skipped by
content hash, changed documents have their chunks replaced, and documents
removed from disk have their chunks deleted, all in one transaction.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional

from sqlalchemy import func

from app.db.models import KnowledgeChunk
from app.db.session import bind_workspace
from app.rag.chunker import DocumentChunk, chunk_documents
from app.rag.document_loader import load_documents
from app.rag.embeddings import MODEL_ID, Embedder, EmbeddingUnavailable, embedder_status, get_embedder
from app.rag.indexer import _tokenize, build_index
from app.rag.knowledge_service import KnowledgeBaseStatus
from app.rag.retriever import KnowledgeRetriever, RetrievalResult, RetrievedChunk, _deduplicate_results
from app.workspace import validate_workspace, workspace_paths

logger = logging.getLogger(__name__)

# multilingual-e5 cosine similarities cluster in ~0.70–0.90. Similarities are
# rescaled to relevance = (sim - floor) / (1 - floor) so the existing
# confidence/coverage thresholds (tuned for TF-IDF scores) stay meaningful;
# chunks at or below the floor are treated as irrelevant.
_DEFAULT_VECTOR_FLOOR = 0.80

_tfidf_lock = threading.Lock()
_tfidf_cache: dict[str, tuple[tuple, KnowledgeRetriever]] = {}


@dataclass
class IngestReport:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    chunks_written: int = 0
    chunks_embedded: int = 0
    embedding_error: str = ""


def _doc_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class WorkspaceKnowledgeService:
    """Knowledge base operations for a single workspace."""

    def __init__(
        self,
        session_factory: Callable,
        workspace: str,
        kb_root: str | Path | None = None,
        *,
        embedder_provider: Callable[[], Embedder] = get_embedder,
        top_k: int = 5,
        min_score: float = 0.01,
        max_chars: int = 800,
        overlap_chars: int = 80,
        vector_floor: float | None = None,
        search_backend: str | None = None,
    ):
        self._factory = session_factory
        self._workspace = validate_workspace(workspace)
        self._kb_root = Path(kb_root) if kb_root else workspace_paths(workspace).kb_root
        self._embedder_provider = embedder_provider
        self._top_k = top_k
        self._min_score = min_score
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars
        self._floor = float(vector_floor if vector_floor is not None
                            else os.environ.get("VECTOR_SCORE_FLOOR", _DEFAULT_VECTOR_FLOOR))
        self._backend_pref = (search_backend or os.environ.get("SEARCH_BACKEND", "auto")).lower()
        self.last_ingest: Optional[IngestReport] = None

    @property
    def workspace(self) -> str:
        return self._workspace

    # ── Plumbing ──────────────────────────────────────────────────────────────

    @contextmanager
    def _session(self) -> Iterator:
        session = bind_workspace(self._factory(), self._workspace)
        try:
            yield session
        finally:
            session.close()

    def _scoped(self, session, *entities):
        query = session.query(*(entities or (KnowledgeChunk,)))
        return query.filter(KnowledgeChunk.workspace == self._workspace)

    def _embedder(self) -> tuple[Optional[Embedder], str]:
        if self._backend_pref == "tfidf":
            return None, "Vector search disabled (SEARCH_BACKEND=tfidf)."
        try:
            return self._embedder_provider(), ""
        except EmbeddingUnavailable as exc:
            return None, str(exc)

    # ── Ingestion (idempotent sync) ───────────────────────────────────────────

    def ingest(self, rebuild: bool = False) -> KnowledgeBaseStatus:
        """Sync the workspace's knowledge base folder into PostgreSQL."""
        report = IngestReport()
        if not self._kb_root.exists():
            logger.warning("Knowledge base folder not found: %s — nothing changed.", self._kb_root)
            report.embedding_error = ""
            self.last_ingest = report
            return self.get_status()

        docs = load_documents(self._kb_root)
        chunks = chunk_documents(docs, max_chars=self._max_chars, overlap_chars=self._overlap_chars)
        by_doc: dict[str, list[DocumentChunk]] = defaultdict(list)
        for chunk in chunks:
            by_doc[chunk.doc_id].append(chunk)
        hashes = {d.doc_id: _doc_hash(d.content) for d in docs}

        embedder, reason = self._embedder()
        report.embedding_error = reason

        with self._session() as session:
            existing: dict[str, dict] = {}
            for doc_id, doc_hash, model in self._scoped(
                session, KnowledgeChunk.doc_id, KnowledgeChunk.doc_hash, KnowledgeChunk.embedding_model
            ):
                info = existing.setdefault(doc_id, {"hash": doc_hash, "count": 0, "embedded": 0})
                info["count"] += 1
                info["embedded"] += int(model == MODEL_ID)

            needs_embedding: list[str] = []
            for doc_id, doc_chunks in by_doc.items():
                prev = existing.get(doc_id)
                same = prev is not None and prev["hash"] == hashes[doc_id] and prev["count"] == len(doc_chunks)
                if same and not rebuild:
                    report.unchanged += 1
                    if embedder is not None and prev["embedded"] < prev["count"]:
                        needs_embedding.append(doc_id)
                    continue
                if prev is not None:
                    self._scoped(session).filter(KnowledgeChunk.doc_id == doc_id).delete(synchronize_session=False)
                    report.updated += 1
                else:
                    report.added += 1
                vectors, embedder, report.embedding_error = self._embed(
                    embedder, [c.text for c in doc_chunks], report.embedding_error
                )
                for i, chunk in enumerate(doc_chunks):
                    session.add(KnowledgeChunk(
                        chunk_id=chunk.chunk_id,
                        doc_id=chunk.doc_id,
                        file_name=chunk.file_name,
                        category=chunk.category,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        chunk_metadata=chunk.metadata,
                        doc_hash=hashes[doc_id],
                        embedding=vectors[i] if vectors else None,
                        embedding_model=MODEL_ID if vectors else None,
                    ))
                report.chunks_written += len(doc_chunks)
                report.chunks_embedded += len(doc_chunks) if vectors else 0

            stale = set(existing) - set(by_doc)
            if stale:
                self._scoped(session).filter(KnowledgeChunk.doc_id.in_(stale)).delete(synchronize_session=False)
                report.removed = len(stale)

            for doc_id in needs_embedding:  # backfill after a model change or an earlier failure
                rows = self._scoped(session).filter(KnowledgeChunk.doc_id == doc_id).order_by(KnowledgeChunk.chunk_index).all()
                vectors, embedder, report.embedding_error = self._embed(
                    embedder, [r.text for r in rows], report.embedding_error
                )
                if not vectors:
                    break
                for row, vector in zip(rows, vectors):
                    row.embedding, row.embedding_model = vector, MODEL_ID
                report.chunks_embedded += len(rows)

            session.commit()

        self._invalidate_tfidf()
        self.last_ingest = report
        logger.info("Knowledge sync [%s]: %s", self._workspace, report)
        return self.get_status()

    @staticmethod
    def _embed(embedder, texts, error):
        """Embed passages; on failure disable embeddings for the rest of this run."""
        if embedder is None or not texts:
            return None, embedder, error
        try:
            return embedder.embed_passages(texts), embedder, error
        except Exception as exc:
            logger.warning("Embedding failed, storing chunks without vectors: %s", exc)
            return None, None, f"Embedding failed: {exc}"

    def rebuild(self) -> KnowledgeBaseStatus:
        """Re-chunk and re-embed every document."""
        return self.ingest(rebuild=True)

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int | None = None, categories: list[str] | None = None) -> RetrievalResult:
        top_k = top_k or self._top_k
        if not query.strip():
            return RetrievalResult(query=query, kb_size=self._count())
        hits, reason, kb_size = self._vector_search([query], limit=top_k * 3)
        if hits is None:
            retriever = self._tfidf_retriever()
            if retriever is None:
                return RetrievalResult(query=query, kb_size=0, fallback_reason=reason)
            result = retriever.retrieve(query, top_k=top_k, categories=categories)
            result.method, result.fallback_reason = "tfidf", reason
            return result
        if categories:
            wanted = {c.lower() for c in categories}
            hits = [(c, s) for c, s in hits if c.category.lower() in wanted]
        hits = _deduplicate_results(hits)[:top_k]
        return self._result(query, hits, kb_size)

    def retrieve_for_job(self, job_description: str, top_k: int = 8) -> RetrievalResult:
        """Job-oriented retrieval: the posting's opening plus its most frequent terms."""
        top_terms = [t for t, _ in Counter(_tokenize(job_description)).most_common(10)]
        queries = [job_description[:500]] + ([" ".join(top_terms)] if top_terms else [])
        hits, reason, kb_size = self._vector_search(queries, limit=top_k)
        if hits is None:
            retriever = self._tfidf_retriever()
            if retriever is None:
                return RetrievalResult(query=job_description[:100], kb_size=0, fallback_reason=reason)
            result = retriever.retrieve_for_job(job_description, top_k=top_k)
            result.method, result.fallback_reason = "tfidf", reason
            return result
        return self._result(job_description[:100], hits[:top_k], kb_size)

    def _result(self, query: str, hits, kb_size: int) -> RetrievalResult:
        chunks = [
            RetrievedChunk(
                chunk_id=c.chunk_id, doc_id=c.doc_id, file_name=c.file_name, category=c.category,
                text=c.text, score=score, chunk_index=c.chunk_index,
            )
            for c, score in hits
        ]
        return RetrievalResult(query=query, chunks=chunks, total_retrieved=len(chunks), kb_size=kb_size, method="vector")

    def _vector_search(self, queries: list[str], limit: int):
        """Return (hits, fallback_reason, kb_size); hits is None when vector search is not usable."""
        embedder, reason = self._embedder()
        if embedder is None:
            return None, reason, 0
        with self._session() as session:
            try:
                kb_size = self._scoped(session, func.count(KnowledgeChunk.id)).scalar() or 0
                embedded = (
                    self._scoped(session, func.count(KnowledgeChunk.id))
                    .filter(KnowledgeChunk.embedding_model == MODEL_ID).scalar() or 0
                )
                if not embedded:
                    return None, "No chunks are embedded with the current model yet — run ingestion.", kb_size
                best: dict[str, tuple[DocumentChunk, float]] = {}
                for q in queries:
                    distance = KnowledgeChunk.embedding.cosine_distance(embedder.embed_query(q)).label("distance")
                    rows = (
                        self._scoped(session, KnowledgeChunk, distance)
                        .filter(KnowledgeChunk.embedding_model == MODEL_ID, KnowledgeChunk.embedding.isnot(None))
                        .order_by(distance)
                        .limit(limit)
                        .all()
                    )
                    for row, dist in rows:
                        relevance = ((1.0 - float(dist)) - self._floor) / (1.0 - self._floor)
                        if relevance <= 0:
                            continue
                        if row.chunk_id not in best or relevance > best[row.chunk_id][1]:
                            best[row.chunk_id] = (_to_chunk(row), relevance)
            except Exception as exc:
                session.rollback()
                logger.warning("Vector search failed — falling back to TF-IDF: %s", exc)
                return None, f"Vector search failed: {exc}", 0
        hits = sorted(best.values(), key=lambda x: x[1], reverse=True)
        return hits, "", kb_size

    def _tfidf_retriever(self) -> Optional[KnowledgeRetriever]:
        """In-memory TF-IDF over this workspace's chunks, rebuilt only when they change."""
        with self._session() as session:
            count, max_id = self._scoped(session, func.count(KnowledgeChunk.id), func.max(KnowledgeChunk.id)).one()
            if not count:
                return None
            fingerprint = (count, max_id)
            with _tfidf_lock:
                cached = _tfidf_cache.get(self._workspace)
                if cached and cached[0] == fingerprint:
                    return cached[1]
            rows = self._scoped(session).order_by(KnowledgeChunk.id).all()
            retriever = KnowledgeRetriever(build_index([_to_chunk(r) for r in rows]), min_score=self._min_score)
        with _tfidf_lock:
            _tfidf_cache[self._workspace] = (fingerprint, retriever)
        return retriever

    def _invalidate_tfidf(self) -> None:
        with _tfidf_lock:
            _tfidf_cache.pop(self._workspace, None)

    # ── Status ────────────────────────────────────────────────────────────────

    def _count(self) -> int:
        with self._session() as session:
            return self._scoped(session, func.count(KnowledgeChunk.id)).scalar() or 0

    def is_ready(self) -> bool:
        return self._count() > 0

    def get_status(self) -> KnowledgeBaseStatus:
        with self._session() as session:
            rows = self._scoped(
                session, KnowledgeChunk.doc_id, KnowledgeChunk.category,
                KnowledgeChunk.embedding_model, KnowledgeChunk.created_at,
            ).all()
        model = embedder_status()
        if not rows:
            return KnowledgeBaseStatus(
                is_indexed=False, kb_root=str(self._kb_root), index_dir="PostgreSQL",
                embedding_model=MODEL_ID, embedding_error=model["error"],
            )
        docs_by_cat: dict[str, set] = defaultdict(set)
        for doc_id, category, _, _ in rows:
            docs_by_cat[category].add(doc_id)
        embedded = sum(1 for r in rows if r[2] == MODEL_ID)
        last = max((r[3] for r in rows if r[3] is not None), default=None)
        vector_ok = embedded > 0 and model["state"] != "unavailable" and self._backend_pref != "tfidf"
        return KnowledgeBaseStatus(
            is_indexed=True,
            total_documents=len({r[0] for r in rows}),
            total_chunks=len(rows),
            categories=sorted(docs_by_cat),
            kb_root=str(self._kb_root),
            index_dir="PostgreSQL",
            last_ingest_timestamp=last.timestamp() if last else None,
            last_ingest_iso=last.isoformat(timespec="seconds") if last else "",
            documents_by_category={c: len(d) for c, d in docs_by_cat.items()},
            search_backend="vector" if vector_ok else "tfidf",
            embedded_chunks=embedded,
            embedding_model=MODEL_ID,
            embedding_error=model["error"],
        )


def _to_chunk(row: KnowledgeChunk) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=row.chunk_id, doc_id=row.doc_id, file_name=row.file_name, category=row.category,
        text=row.text, chunk_index=row.chunk_index, metadata=row.chunk_metadata or {},
    )
