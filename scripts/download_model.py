"""
download_model.py — Download the pinned embedding model into MODEL_CACHE_DIR.

Run once for local use, or at Docker build time so the image works offline:
    python scripts/download_model.py
    python scripts/download_model.py --verify     # also load it and embed a test sentence
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the local embedding model.")
    parser.add_argument("--verify", action="store_true", help="Load the model and embed a test sentence.")
    args = parser.parse_args()

    from app.rag.embeddings import MODEL_ID, Embedder, model_cache_dir, resolve_model_path  # noqa: PLC0415

    path = resolve_model_path(allow_download=True)
    print(f"Model {MODEL_ID} available at {path} (cache: {model_cache_dir()})")
    if args.verify:
        vector = Embedder(path).embed_query("Kubernetes platform engineer / מהנדס פלטפורמה")
        print(f"Verified: {len(vector)}-dimensional embedding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
