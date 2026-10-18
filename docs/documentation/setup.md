# Setup and configuration

## Requirements

- Docker Desktop (or Docker Engine) with Compose v2.
- About 4 GB of disk for the image. It contains CPU-only PyTorch and the 470 MB embedding model.
- Internet access **only while building the image** (Python packages and the one-time model download). The running containers need no network for embeddings.

## First start

```bash
cp .env.example .env            # then replace both change-me passwords (letters/digits/-/_ only)
docker compose up -d --build    # db → migrate → app
```

Open <http://localhost:8086>. Change the host port with `APP_HOST_PORT` in `.env`. The container port stays 8508.

### Create your login (owner)

```bash
docker compose run --rm tools scripts/create_user.py oren --workspace personal
```

The script asks for the password twice without echoing it (minimum 8 characters). It stores only a bcrypt hash in `config/users.yaml`. That file is git-ignored, excluded from the Docker build context and mounted **read-only** into the `app` container. Run the same command again to change the password.

### Demo account (optional)

```bash
docker compose run --rm tools scripts/seed_demo.py
```

This creates the login **demo / demo2026** (if missing) and loads synthetic jobs, documents and tracker rows into the demo workspace. It is idempotent: running it again duplicates nothing.

### Your documents

Put your career documents (`.md`, `.txt`, `.pdf`, `.json`) under `knowledge_base/`, for example `knowledge_base/resume/`, `knowledge_base/projects/`, `knowledge_base/skills/`. The folder is mounted read-only into the app and is git-ignored. Then click **Sync knowledge base** in the app.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `career_owner` / — / `career` | Owner role, used only by `migrate`. |
| `APP_DB_USER` / `APP_DB_PASSWORD` | `career_app` / — | Least-privilege role used by the app and tools. |
| `APP_HOST_PORT` | `8086` | Host port of the web app. |
| `DB_HOST_PORT` | `5433` | Host port of PostgreSQL (bound to 127.0.0.1) for local tools and tests. |
| `SESSION_TIMEOUT_MINUTES` | `60` | Inactivity timeout (overrides `session_timeout_minutes` in `users.yaml`). |
| `SEARCH_BACKEND` | `auto` | `auto` = vector search with TF-IDF fallback; `tfidf` forces keyword search. |
| `VECTOR_SCORE_FLOOR` | `0.80` | Cosine similarity treated as "no relevance". |
| `APP_TIMEZONE` | `Asia/Jerusalem` | Calendar day used for "days since submission" and the 14-day rule. |

## Embedding model

- Model: `intfloat/multilingual-e5-small`, revision `614241f6…`, 384 dimensions. It covers about 100 languages, including English and Hebrew. Inputs longer than 512 tokens are truncated. Retrieval was verified on the synthetic demo documents with English and Hebrew questions; cross-language matching (e.g. a Hebrew question against English documents) is supported by the model but was not separately benchmarked. Quality on long or highly specialised Hebrew text has not been benchmarked.
- **Docker**: downloaded during `docker compose build` into `/opt/models` and loaded with `HF_HUB_OFFLINE=1`. Verified to work with networking disabled (`docker run --network none`).
- **Outside Docker**: downloaded once (~470 MB) into `data/models/` on first use, or explicitly with `python scripts/download_model.py --verify`. Set `EMBEDDING_ALLOW_DOWNLOAD=false` to forbid downloads.
- If the model cannot be loaded, the Knowledge Base page shows the reason and search uses TF-IDF.

## Running outside Docker (development)

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
docker compose up -d db migrate                     # PostgreSQL + schema
export DATABASE_URL=postgresql+psycopg://career_app:<APP_DB_PASSWORD>@127.0.0.1:5433/career
streamlit run dashboard/streamlit_app.py
```

Command-line scripts (`fetch_jobs.py`, `score_jobs.py`, `ingest_knowledge.py`, …) take `--workspace personal|demo` (default: `$WORKSPACE`, else `personal`).

## Tests

```bash
pytest                                  # unit + UI tests (SQLite, no services needed)
TEST_PG_ADMIN_URL=postgresql+psycopg://<superuser>:<password>@127.0.0.1:<port>/postgres pytest tests/integration
```

The integration tests create and drop their own throwaway database and role. Point them at a disposable PostgreSQL + pgvector server, for example:

```bash
docker run -d --name cia-test-pg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -p 127.0.0.1:55432:5432 pgvector/pgvector:pg16
TEST_PG_ADMIN_URL=postgresql+psycopg://test:test@127.0.0.1:55432/postgres pytest tests/integration
```

Tests marked `model` load the real embedding model and are skipped if it is not cached locally.
