"""
embeddings.py — Local sentence-transformers embeddings for knowledge-base search.

Model: intfloat/multilingual-e5-small (384 dimensions, max 512 tokens),
pinned to a fixed revision. It is trained on ~100 languages including English
and Hebrew, runs on CPU, and needs no API key or hosted inference service.
E5 models expect "query: " / "passage: " prefixes, which this module adds.

Model files:
- Docker: downloaded at image build time (scripts/download_model.py) into
  MODEL_CACHE_DIR and loaded with HF_HUB_OFFLINE=1 — no runtime network.
- Local runs: downloaded once on first use into MODEL_CACHE_DIR
  (default data/models/, git-ignored) unless EMBEDDING_ALLOW_DOWNLOAD=false.

Any failure (missing package, missing files, wrong dimension) is captured as
an "unavailable" status; callers fall back to TF-IDF retrieval.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from app.rag.model_spec import (  # noqa: F401  (re-exported)
    EMBEDDING_DIM, MODEL_FILES, MODEL_ID, MODEL_NAME, MODEL_REVISION, model_cache_dir,
)

logger = logging.getLogger(__name__)

_RETRY_AFTER_SECONDS = 300


class EmbeddingUnavailable(RuntimeError):
    """The embedding model cannot be used; retrieval should fall back to TF-IDF."""


def _downloads_allowed() -> bool:
    if os.environ.get("HF_HUB_OFFLINE", "").lower() in ("1", "true", "yes"):
        return False
    return os.environ.get("EMBEDDING_ALLOW_DOWNLOAD", "true").lower() in ("1", "true", "yes")


def resolve_model_path(allow_download: bool | None = None) -> Path:
    """Return the local snapshot directory, downloading it first if allowed."""
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    allow = _downloads_allowed() if allow_download is None else allow_download
    kwargs: dict[str, Any] = dict(
        repo_id=MODEL_NAME,
        revision=MODEL_REVISION,
        cache_dir=str(model_cache_dir()),
        allow_patterns=MODEL_FILES,
    )
    try:
        return Path(snapshot_download(local_files_only=True, **kwargs))
    except Exception:
        if not allow:
            raise EmbeddingUnavailable(
                f"Model files for {MODEL_ID} are not in {model_cache_dir()} and downloads are disabled. "
                "Run `python scripts/download_model.py`."
            )
    try:  # Use the OS certificate store when available (corporate TLS inspection on Windows).
        import truststore  # noqa: PLC0415
        truststore.inject_into_ssl()
    except Exception:
        pass
    logger.info("Downloading embedding model %s (one-time, ~470 MB)...", MODEL_ID)
    return Path(snapshot_download(**kwargs))


class Embedder:
    """Thin wrapper around a SentenceTransformer with E5 prefixes and L2 normalisation."""

    model_id = MODEL_ID
    dimension = EMBEDDING_DIM

    def __init__(self, model_path: Path):
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        self._model = SentenceTransformer(str(model_path), device="cpu")
        dim = self._model.get_sentence_embedding_dimension()
        if dim != EMBEDDING_DIM:
            raise EmbeddingUnavailable(
                f"Model {MODEL_ID} produces {dim}-d vectors but the database column is {EMBEDDING_DIM}-d."
            )

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"passage: {t}" for t in texts]) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"])[0]


# ── Process-wide singleton with failure status ───────────────────────────────

_lock = threading.Lock()
_embedder: Optional[Embedder] = None
_error: str = ""
_failed_at: float = 0.0


def get_embedder() -> Embedder:
    """Return the shared Embedder or raise EmbeddingUnavailable (retried every 5 minutes)."""
    global _embedder, _error, _failed_at
    if _embedder is not None:
        return _embedder
    with _lock:
        if _embedder is not None:
            return _embedder
        if _error and time.monotonic() - _failed_at < _RETRY_AFTER_SECONDS:
            raise EmbeddingUnavailable(_error)
        try:
            _embedder = Embedder(resolve_model_path())
            _error = ""
            logger.info("Embedding model loaded: %s", MODEL_ID)
            return _embedder
        except EmbeddingUnavailable as exc:
            _error = str(exc)
        except ImportError as exc:
            _error = f"sentence-transformers is not installed ({exc})."
        except Exception as exc:  # corrupt files, OOM, etc.
            _error = f"Could not load embedding model {MODEL_ID}: {exc}"
        _failed_at = time.monotonic()
        logger.warning("Embeddings unavailable — TF-IDF fallback in use. %s", _error)
        raise EmbeddingUnavailable(_error)


def embedder_status() -> dict[str, str]:
    """Current model state for status displays: ready | unavailable | not_loaded."""
    if _embedder is not None:
        return {"state": "ready", "model": MODEL_ID, "error": ""}
    if _error:
        return {"state": "unavailable", "model": MODEL_ID, "error": _error}
    return {"state": "not_loaded", "model": MODEL_ID, "error": ""}


def reset_embedder() -> None:
    """Forget the cached model/failure (tests, or retry after fixing the cache)."""
    global _embedder, _error, _failed_at
    with _lock:
        _embedder, _error, _failed_at = None, "", 0.0
