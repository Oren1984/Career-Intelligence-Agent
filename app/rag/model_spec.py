"""model_spec.py — The pinned local embedding model (dependency-free, shared by app and Docker build)."""
from __future__ import annotations

import os
from pathlib import Path

MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
MODEL_REVISION = os.environ.get("EMBEDDING_MODEL_REVISION", "614241f622f53c4eeff9890bdc4f31cfecc418b3")
MODEL_ID = f"{MODEL_NAME}@{MODEL_REVISION[:12]}"   # stored with every embedding
EMBEDDING_DIM = 384                                 # vector(384) column in knowledge_chunks

# Only the files sentence-transformers needs (skips ONNX/OpenVINO/pytorch .bin copies).
MODEL_FILES = [
    "config.json", "modules.json", "sentence_bert_config.json", "tokenizer.json",
    "tokenizer_config.json", "special_tokens_map.json", "sentencepiece.bpe.model",
    "model.safetensors", "1_Pooling/config.json",
]

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def model_cache_dir() -> Path:
    return Path(os.environ.get("MODEL_CACHE_DIR", _REPO_ROOT / "data" / "models"))
