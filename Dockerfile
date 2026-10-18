# Dockerfile for the Career Intelligence Agent (V2.0)
#
# - CPU-only PyTorch + sentence-transformers for local embeddings.
# - The pinned embedding model is downloaded at build time into /opt/models,
#   so the running container needs no network access for embeddings.
# - Runs as a non-root user. Startup only launches the dashboard: schema
#   migrations run in the separate `migrate` service, and jobs are collected
#   and scored only when explicitly requested.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MODEL_CACHE_DIR=/opt/models

WORKDIR /app

# Dependencies (layer cache): CPU torch first so sentence-transformers does not pull CUDA wheels.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.10.0" \
 && pip install -r requirements.txt

# Embedding model (layer cache): only the model spec and downloader are needed.
COPY app/__init__.py app/__init__.py
COPY app/rag/__init__.py app/rag/model_spec.py app/rag/embeddings.py app/rag/
COPY scripts/__init__.py scripts/download_model.py scripts/
RUN python scripts/download_model.py --verify \
 && chmod -R a+rX /opt/models

# Application source.
COPY . .

RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /app/data \
 && chown -R appuser:appuser /app/data
USER appuser

# Embeddings load from the baked cache only; no runtime downloads.
ENV HF_HUB_OFFLINE=1 \
    EMBEDDING_ALLOW_DOWNLOAD=false

EXPOSE 8508

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8508/_stcore/health', timeout=4).status == 200 else 1)"

CMD ["streamlit", "run", "dashboard/streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8508", \
     "--server.headless=true", "--browser.gatherUsageStats=false", \
     "--server.fileWatcherType=none"]
