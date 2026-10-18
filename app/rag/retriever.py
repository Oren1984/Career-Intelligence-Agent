"""
retriever.py — High-level retrieval interface over the local knowledge index.

Wraps indexer.query_index with:
- Structured result objects
- Category filtering
- Score threshold filtering
- Deduplication of overlapping chunks

Local-only. No network calls. No cloud services.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.rag.chunker import DocumentChunk
from app.rag.indexer import LocalIndex, query_index

logger = logging.getLogger(__name__)


# ── Result model ──────────────────────────────────────────────────────────────

@dataclass
class RetrievedChunk:
    """A retrieved chunk with its relevance score and provenance."""
    chunk_id: str
    doc_id: str
    file_name: str
    category: str
    text: str
    score: float
    chunk_index: int

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "file_name": self.file_name,
            "category": self.category,
            "text": self.text,
            "score": round(self.score, 4),
        }

    def short_summary(self) -> str:
        """A short display string for UI."""
        preview = self.text[:200].replace("\n", " ")
        if len(self.text) > 200:
            preview += "…"
        return f"[{self.category}/{self.file_name}] {preview}"


@dataclass
class RetrievalResult:
    """Complete retrieval result for a query."""
    query: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    total_retrieved: int = 0
    kb_size: int = 0               # Total chunks in index
    method: str = "tfidf"          # "vector" (pgvector) or "tfidf"
    fallback_reason: str = ""      # why vector search was not used, if it was attempted

    def has_evidence(self) -> bool:
        return bool(self.chunks)

    def top_chunk(self) -> Optional[RetrievedChunk]:
        return self.chunks[0] if self.chunks else None

    def as_context_string(self, max_chunks: int = 5) -> str:
        """Format retrieved chunks as a readable context block."""
        if not self.chunks:
            return "No relevant evidence found in local knowledge base."
        lines = []
        for i, chunk in enumerate(self.chunks[:max_chunks], 1):
            lines.append(
                f"[Evidence {i} | {chunk.category} | {chunk.file_name} | score: {chunk.score:.3f}]\n"
                f"{chunk.text}"
            )
        return "\n\n---\n\n".join(lines)


# ── Retriever ─────────────────────────────────────────────────────────────────

class KnowledgeRetriever:
    """
    Retrieves relevant chunks from the local knowledge base.

    Usage:
        retriever = KnowledgeRetriever(index)
        result = retriever.retrieve("Docker and Kubernetes experience")
        print(result.as_context_string())
    """

    def __init__(
        self,
        index: LocalIndex,
        min_score: float = 0.01,
        deduplicate: bool = True,
    ):
        self._index = index
        self._min_score = min_score
        self._deduplicate = deduplicate

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        categories: list[str] | None = None,
    ) -> RetrievalResult:
        """
        Retrieve top-k relevant chunks for the given query.

        Args:
            query: Natural language query string.
            top_k: Maximum number of chunks to return.
            categories: If specified, only return chunks from these categories.

        Returns:
            RetrievalResult with ranked chunks.
        """
        if not self._index or not self._index.chunks:
            return RetrievalResult(query=query, kb_size=0)

        # Fetch more than top_k so we have room to filter
        raw_results = query_index(self._index, query, top_k=top_k * 3)

        # Filter by score threshold
        filtered = [
            (chunk, score)
            for chunk, score in raw_results
            if score >= self._min_score
        ]

        # Filter by category if requested
        if categories:
            cat_set = {c.lower() for c in categories}
            filtered = [
                (chunk, score) for chunk, score in filtered
                if chunk.category.lower() in cat_set
            ]

        # Deduplicate: skip chunks from the same doc that are too similar
        if self._deduplicate:
            filtered = _deduplicate_results(filtered)

        # Take top_k
        final = filtered[:top_k]

        retrieved = [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                file_name=chunk.file_name,
                category=chunk.category,
                text=chunk.text,
                score=score,
                chunk_index=chunk.chunk_index,
            )
            for chunk, score in final
        ]

        return RetrievalResult(
            query=query,
            chunks=retrieved,
            total_retrieved=len(retrieved),
            kb_size=len(self._index.chunks),
        )

    def retrieve_for_job(self, job_description: str, top_k: int = 8) -> RetrievalResult:
        """
        Specialized retrieval for job analysis.

        Runs multiple targeted sub-queries and merges results, giving broader
        coverage than a single query.

        Args:
            job_description: Full job description text.
            top_k: Total chunks to return across all sub-queries.

        Returns:
            Merged RetrievalResult.
        """
        from app.rag.indexer import _tokenize  # noqa: PLC0415

        # Extract key terms from the job description for targeted queries
        tokens = _tokenize(job_description)
        # Use the most frequent meaningful tokens as sub-queries
        from collections import Counter  # noqa: PLC0415
        term_freq = Counter(tokens)
        top_terms = [t for t, _ in term_freq.most_common(20)]

        # Build sub-queries: full job text + skill-focused queries
        queries = [job_description[:500]]  # First 500 chars of JD
        if top_terms:
            queries.append(" ".join(top_terms[:10]))  # Top terms

        all_chunks: list[tuple[DocumentChunk, float]] = []
        seen_ids: set[str] = set()

        for q in queries:
            raw = query_index(self._index, q, top_k=top_k)
            for chunk, score in raw:
                if chunk.chunk_id not in seen_ids and score >= self._min_score:
                    all_chunks.append((chunk, score))
                    seen_ids.add(chunk.chunk_id)

        # Sort by score and take top_k
        all_chunks.sort(key=lambda x: x[1], reverse=True)
        final = all_chunks[:top_k]

        retrieved = [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                file_name=chunk.file_name,
                category=chunk.category,
                text=chunk.text,
                score=score,
                chunk_index=chunk.chunk_index,
            )
            for chunk, score in final
        ]

        return RetrievalResult(
            query=job_description[:100],
            chunks=retrieved,
            total_retrieved=len(retrieved),
            kb_size=len(self._index.chunks),
        )


def _deduplicate_results(
    results: list[tuple[DocumentChunk, float]],
) -> list[tuple[DocumentChunk, float]]:
    """
    Remove near-duplicate chunks from the same document.
    Keeps the highest-scoring chunk per (doc_id, adjacent chunk_index) group.
    """
    seen: dict[str, float] = {}  # doc_id → best score seen
    deduped = []

    for chunk, score in results:
        # Allow multiple chunks from same doc, but not adjacent chunks
        key = f"{chunk.doc_id}::{chunk.chunk_index}"
        if key in seen:
            continue
        # Also skip if immediately adjacent chunk already selected
        adjacent_key = f"{chunk.doc_id}::{chunk.chunk_index - 1}"
        if adjacent_key in seen:
            continue
        seen[key] = score
        deduped.append((chunk, score))

    return deduped
