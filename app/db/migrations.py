# db/migrations.py
# Schema creation and versioned PostgreSQL migrations (idempotent).

"""Schema initialization and migrations.

Run by ``scripts/init_db.py`` (the Compose ``migrate`` service) with the
database owner credentials. Every step is idempotent, so re-running on an
existing database is safe. Steps:

1. ``CREATE EXTENSION vector`` (PostgreSQL).
2. ``create_all`` for ORM tables that do not exist yet.
3. Legacy V1→V2 column additions on ``scores`` (kept for old SQLite files).
4. Versioned PostgreSQL migrations recorded in ``schema_migrations``.
5. Row-level security policies on every workspace table.
6. The application role (``APP_DB_USER``): login, no superuser, no BYPASSRLS,
   DML-only grants. The app never owns tables, so it cannot drop them or
   disable row-level security.
"""
from __future__ import annotations

import logging
import os
import re

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from app.db.models import Base, WORKSPACE_TABLES

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_ADVISORY_LOCK_KEY = 72_514_001  # serialises concurrent migration runs

# Legacy V2 columns added to an existing V1 ``scores`` table.
_LEGACY_SCORE_COLUMNS = [
    ("keyword_score", "ALTER TABLE scores ADD COLUMN keyword_score REAL"),
    ("semantic_score", "ALTER TABLE scores ADD COLUMN semantic_score REAL"),
    ("final_score", "ALTER TABLE scores ADD COLUMN final_score REAL"),
    ("matched_themes", "ALTER TABLE scores ADD COLUMN matched_themes TEXT"),
    ("missing_themes", "ALTER TABLE scores ADD COLUMN missing_themes TEXT"),
]

# version → statements. Append new versions; never edit applied ones.
_PG_MIGRATIONS: dict[int, list[str]] = {
    1: [
        # Cosine HNSW index: embeddings are L2-normalised and queried with <=>.
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)",
        "CREATE INDEX IF NOT EXISTS ix_applications_workspace_status ON applications (workspace, status)",
        "CREATE INDEX IF NOT EXISTS ix_applications_workspace_submitted ON applications (workspace, submitted_date)",
    ],
}

_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class SchemaNotReady(RuntimeError):
    """Raised when the database has not been migrated to SCHEMA_VERSION."""


def apply_legacy_score_columns(conn: Connection) -> None:
    """Add V2 columns to a V1 ``scores`` table if they are absent."""
    inspector = inspect(conn)
    if "scores" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("scores")}
    for col_name, alter_sql in _LEGACY_SCORE_COLUMNS:
        if col_name not in existing:
            conn.execute(text(alter_sql))
            logger.info("Legacy migration: added column '%s' to scores.", col_name)


def run_migrations(engine: Engine) -> None:
    """Bring the schema to SCHEMA_VERSION. Safe to run repeatedly."""
    pg = engine.dialect.name == "postgresql"
    with engine.connect() as conn:
        if pg:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
            conn.commit()
        try:
            if pg:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            Base.metadata.create_all(conn)
            apply_legacy_score_columns(conn)
            conn.commit()
            if pg:
                _apply_versioned(conn)
                _apply_row_level_security(conn)
                _ensure_app_role(conn)
                conn.commit()
        finally:
            if pg:
                conn.rollback()
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
                conn.commit()


def _apply_versioned(conn: Connection) -> None:
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY,"
        " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    ))
    applied = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}
    for version in sorted(_PG_MIGRATIONS):
        if version in applied:
            continue
        for statement in _PG_MIGRATIONS[version]:
            conn.execute(text(statement))
        conn.execute(text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": version})
        logger.info("Applied schema migration %d.", version)


def _apply_row_level_security(conn: Connection) -> None:
    """(Re)create the workspace isolation policy on every workspace table."""
    predicate = "workspace = current_setting('app.workspace', true)"
    for table in WORKSPACE_TABLES:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(text(f"DROP POLICY IF EXISTS workspace_isolation ON {table}"))
        conn.execute(text(
            f"CREATE POLICY workspace_isolation ON {table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        ))


_ROLE_SETUP = """
DO $role$
DECLARE
    r text := current_setting('cia.app_role');
    p text := current_setting('cia.app_password');
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r) THEN
        EXECUTE format('CREATE ROLE %I LOGIN', r);
    END IF;
    EXECUTE format('ALTER ROLE %I WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD %L', r, p);
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), r);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', r);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', r);
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE ON schema_migrations FROM %I', r);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', r);
END
$role$
"""


def _ensure_app_role(conn: Connection) -> None:
    """Create/update the least-privilege application role from APP_DB_USER/APP_DB_PASSWORD.

    Values are passed as bound parameters into transaction-local settings and
    the statements are built server-side with format(%I/%L), so no credential
    is ever interpolated into SQL text on the client.
    """
    role = os.environ.get("APP_DB_USER", "").strip()
    password = os.environ.get("APP_DB_PASSWORD", "")
    if not role or not password:
        logger.info("APP_DB_USER/APP_DB_PASSWORD not set; skipping application role setup.")
        return
    if not _ROLE_RE.match(role):
        raise ValueError("APP_DB_USER must be a lowercase PostgreSQL identifier.")
    if role == conn.execute(text("SELECT current_user")).scalar_one():
        raise ValueError("APP_DB_USER must differ from the migration (owner) user.")

    conn.execute(
        text("SELECT set_config('cia.app_role', :r, true), set_config('cia.app_password', :p, true)"),
        {"r": role, "p": password},
    )
    conn.execute(text(_ROLE_SETUP))
    logger.info("Application role '%s' configured (DML only, row-level security enforced).", role)


def assert_schema_current(engine: Engine) -> None:
    """Raise SchemaNotReady unless migrations reached SCHEMA_VERSION."""
    with engine.connect() as conn:
        try:
            version = conn.execute(text("SELECT max(version) FROM schema_migrations")).scalar()
        except Exception as exc:
            raise SchemaNotReady(
                "Database schema is missing. Run `python scripts/init_db.py` with the owner "
                "credentials (Docker: the `migrate` service runs it automatically)."
            ) from exc
    if (version or 0) < SCHEMA_VERSION:
        raise SchemaNotReady(f"Database schema is at version {version}, expected {SCHEMA_VERSION}.")
