"""
indexer.py — Build and persist a local TF-IDF index over DocumentChunks.

Design:
- Pure Python TF-IDF implementation (no external deps required)
- Optional: scikit-learn TfidfVectorizer for higher quality (if installed)
- Index stored as a JSON file in data/knowledge_index/
- Includes chunk metadata for source attribution

Privacy: all data stays local. No network calls.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.rag.chunker import DocumentChunk

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "knowledge_index",
)
_INDEX_FILE = "index.json"
_CHUNKS_FILE = "chunks.json"
_META_FILE = "metadata.json"


# ── Tokenizer ─────────────────────────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "dare",
    "ought", "used", "i", "you", "he", "she", "it", "we", "they", "my",
    "your", "his", "her", "its", "our", "their", "this", "that", "these",
    "those", "as", "if", "then", "than", "so", "yet", "both", "not",
    "also", "just", "very", "more", "most", "such", "each", "all", "any",
})


def _tokenize(text: str) -> list[str]:
    """Lowercase, remove punctuation, split, remove stop words.

    Accepts Latin and Hebrew letters (U+05D0–U+05EA) so Hebrew documents remain
    searchable through the TF-IDF fallback; English tokenization is unchanged.
    """
    tokens = re.findall(r'\b[a-zא-ת][a-z0-9א-ת+#./_-]{1,}\b', text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) >= 2]


# ── Pure Python TF-IDF ────────────────────────────────────────────────────────

def _compute_tf(tokens: list[str]) -> dict[str, float]:
    counts = Counter(tokens)
    total = max(len(tokens), 1)
    return {term: count / total for term, count in counts.items()}


def _build_inverted_index(tokenized_docs: list[list[str]]) -> dict[str, list[int]]:
    """Maps term → list of document indices that contain it."""
    inv: dict[str, list[int]] = {}
    for doc_i, tokens in enumerate(tokenized_docs):
        for term in set(tokens):
            inv.setdefault(term, []).append(doc_i)
    return inv


def _compute_idf(term: str, inv_index: dict[str, list[int]], n_docs: int) -> float:
    df = len(inv_index.get(term, []))
    if df == 0:
        return 0.0
    return math.log((1 + n_docs) / (1 + df)) + 1.0


def _tfidf_vector(
    tokens: list[str],
    inv_index: dict[str, list[int]],
    n_docs: int,
) -> dict[str, float]:
    tf = _compute_tf(tokens)
    return {
        term: tf_val * _compute_idf(term, inv_index, n_docs)
        for term, tf_val in tf.items()
    }


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Sparse cosine similarity between two TF-IDF vectors."""
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(vec_a.get(t, 0.0) * v for t, v in vec_b.items())
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Index structure ───────────────────────────────────────────────────────────

@dataclass
class LocalIndex:
    """Serializable TF-IDF index over document chunks."""
    chunks: list[DocumentChunk]
    tfidf_vectors: list[dict[str, float]]    # One per chunk
    inv_index: dict[str, list[int]]          # term → chunk indices
    n_docs: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "file_name": c.file_name,
                    "category": c.category,
                    "text": c.text,
                    "chunk_index": c.chunk_index,
                    "metadata": c.metadata,
                }
                for c in self.chunks
            ],
            "tfidf_vectors": self.tfidf_vectors,
            "inv_index": self.inv_index,
            "n_docs": self.n_docs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocalIndex":
        chunks = [
            DocumentChunk(
                chunk_id=c["chunk_id"],
                doc_id=c["doc_id"],
                file_name=c["file_name"],
                category=c["category"],
                text=c["text"],
                chunk_index=c["chunk_index"],
                metadata=c.get("metadata", {}),
            )
            for c in data["chunks"]
        ]
        return cls(
            chunks=chunks,
            tfidf_vectors=data["tfidf_vectors"],
            inv_index=data["inv_index"],
            n_docs=data["n_docs"],
        )


# ── Public API ────────────────────────────────────────────────────────────────

def build_index(chunks: list[DocumentChunk]) -> LocalIndex:
    """
    Build a TF-IDF index from a list of DocumentChunks.

    Uses pure Python implementation (no external deps).

    Args:
        chunks: Chunks to index.

    Returns:
        LocalIndex ready for querying.
    """
    if not chunks:
        logger.warning("build_index called with empty chunk list.")
        return LocalIndex(chunks=[], tfidf_vectors=[], inv_index={}, n_docs=0)

    logger.info("Building TF-IDF index over %d chunks...", len(chunks))

    tokenized = [_tokenize(c.text) for c in chunks]
    inv_index = _build_inverted_index(tokenized)
    n_docs = len(chunks)

    tfidf_vectors = [
        _tfidf_vector(tokens, inv_index, n_docs)
        for tokens in tokenized
    ]

    logger.info("Index built: %d unique terms, %d chunks.", len(inv_index), n_docs)
    return LocalIndex(
        chunks=chunks,
        tfidf_vectors=tfidf_vectors,
        inv_index=inv_index,
        n_docs=n_docs,
    )


def save_index(index: LocalIndex, index_dir: str | None = None) -> str:
    """
    Persist the index to disk as JSON.

    Args:
        index: The index to save.
        index_dir: Directory to save to. Defaults to data/knowledge_index/.

    Returns:
        Path to the saved index file.
    """
    save_dir = Path(index_dir or _DEFAULT_INDEX_DIR)
    save_dir.mkdir(parents=True, exist_ok=True)

    index_path = save_dir / _INDEX_FILE
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index.to_dict(), fh, ensure_ascii=False, indent=2)

    logger.info("Index saved to %s (%d chunks).", index_path, len(index.chunks))
    return str(index_path)


def load_index(index_dir: str | None = None) -> LocalIndex | None:
    """
    Load a previously saved index from disk.

    Args:
        index_dir: Directory to load from. Defaults to data/knowledge_index/.

    Returns:
        LocalIndex or None if not found.
    """
    load_dir = Path(index_dir or _DEFAULT_INDEX_DIR)
    index_path = load_dir / _INDEX_FILE

    if not index_path.exists():
        logger.info("No saved index found at %s.", index_path)
        return None

    try:
        with open(index_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        index = LocalIndex.from_dict(data)
        logger.info("Loaded index: %d chunks from %s.", len(index.chunks), index_path)
        return index
    except Exception as exc:
        logger.warning("Failed to load index from %s: %s", index_path, exc)
        return None


def query_index(
    index: LocalIndex,
    query: str,
    top_k: int = 5,
) -> list[tuple[DocumentChunk, float]]:
    """
    Retrieve top-k chunks most relevant to the query using TF-IDF cosine similarity.

    Args:
        index: The loaded index.
        query: Query string.
        top_k: Number of results to return.

    Returns:
        List of (DocumentChunk, score) sorted by descending relevance.
    """
    if not index.chunks or not query.strip():
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    query_vec = _tfidf_vector(query_tokens, index.inv_index, index.n_docs)

    scored = [
        (chunk, _cosine_similarity(query_vec, vec))
        for chunk, vec in zip(index.chunks, index.tfidf_vectors)
    ]

    scored.sort(key=lambda x: x[1], reverse=True)
    return [(chunk, score) for chunk, score in scored[:top_k] if score > 0.0]
