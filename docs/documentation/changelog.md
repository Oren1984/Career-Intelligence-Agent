# Changelog

## V2.0 — 2026-10-18

### Added

- **PostgreSQL 16 + pgvector** persistence (Docker Compose `db` service with health check and named volume; one-shot `migrate` service).
- **Sign-in** with bcrypt-hashed local credentials (`config/users.yaml`), logout, inactivity timeout and failed-login throttling. Logins: `oren` (personal workspace; you set its password locally) and `demo` (synthetic data workspace).
- **Workspace isolation** enforced by PostgreSQL row-level security and a least-privilege application role.
- **Semantic knowledge search** with the local `intfloat/multilingual-e5-small` model (English and Hebrew), an idempotent document sync and an automatic TF-IDF fallback.
- **Application Tracker** with Excel import (preview, duplicate and validation reporting, lossless round-trip) and export matching `Job_Search_Tracker.xlsx`.
- **Dashboard**: the workbook's four KPIs, distributions, weekly submissions, pipeline funnel and a 14-day follow-up list.
- **English / Hebrew** interface with RTL layout and per-account language memory.
- **Help Center**: searchable articles in both languages, with contextual Help buttons.
- Demo seeding script, user-creation script, model download script, integration tests against PostgreSQL.

### Changed

- The Streamlit UI is split into pages with sidebar navigation, KPI cards, Altair charts and consistent empty and error states. All V1 pages and execution modes are kept.
- The app is published on **<http://localhost:8086>**.
- The container no longer collects or scores jobs at startup; collection and scoring run only from *Job pipeline* or the CLI.
- Timestamps are timezone-aware UTC throughout.
- *Reset job data* now deletes only the signed-in workspace's job rows instead of dropping all tables.
- Development dependencies moved to `requirements-dev.txt`.

### Removed

- CI workflows (`.github/workflows`).
- The inactive n8n integration (`automation/`).
- The static site and notebook (removed before the upgrade) and the knowledge-base sample files.

### Unchanged

- Job collection, deduplication, classic and career scoring, ranking, recommendation labels and the Hybrid / Agent Only / RAG Only execution modes.
