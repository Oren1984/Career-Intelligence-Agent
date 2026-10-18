# db/session.py
# this file initializes the database connection and provides access to the database session

"""Database engine, session management and workspace binding.

- One engine (and connection pool) per database URL per process; Streamlit
  reruns and scripts reuse it instead of creating a pool per call.
- ``DATABASE_URL`` must be set. PostgreSQL is the runtime database; SQLite
  URLs remain usable for unit tests and throwaway local experiments.
- A session bound to a workspace (``get_session(workspace=...)``) sets the
  transaction-local ``app.workspace`` setting at the start of every
  transaction. PostgreSQL row-level security uses it to expose only that
  workspace's rows, and new rows are stamped with it before flush.
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.workspace import validate_workspace

logger = logging.getLogger(__name__)

_ENGINES: dict[str, Engine] = {}
_FACTORIES: dict[str, sessionmaker] = {}
_LOCK = threading.Lock()


class DatabaseNotConfigured(RuntimeError):
    """Raised when DATABASE_URL is missing."""


def database_url(db_url: str | None = None) -> str:
    url = db_url or os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseNotConfigured(
            "DATABASE_URL is not set. Start PostgreSQL with `docker compose up -d db` "
            "and export DATABASE_URL (see .env.example)."
        )
    return url


def is_postgres(engine_or_url) -> bool:
    url = str(getattr(engine_or_url, "url", engine_or_url))
    return url.startswith("postgresql")


def get_engine(db_url: str | None = None) -> Engine:
    """Return the process-wide engine for ``db_url`` (created once)."""
    url = database_url(db_url)
    engine = _ENGINES.get(url)
    if engine is not None:
        return engine
    with _LOCK:
        engine = _ENGINES.get(url)
        if engine is None:
            if url.startswith("sqlite"):
                path = url.replace("sqlite:///", "", 1)
                if path and path != ":memory:" and os.path.dirname(path):
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                engine = create_engine(url, connect_args={"check_same_thread": False})
            else:
                engine = create_engine(
                    url,
                    pool_pre_ping=True,
                    pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
                    max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "5")),
                    pool_recycle=1800,
                )
            _ENGINES[url] = engine
    return engine


def get_session_factory(db_url: str | None = None) -> sessionmaker:
    """Return the cached session factory for the engine of ``db_url``."""
    url = database_url(db_url)
    factory = _FACTORIES.get(url)
    if factory is None:
        engine = get_engine(url)  # takes _LOCK itself; must not be called while holding it
        with _LOCK:
            factory = _FACTORIES.get(url)
            if factory is None:
                factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
                _FACTORIES[url] = factory
    return factory


def bind_workspace(session: Session, workspace: str) -> Session:
    """Bind ``session`` to ``workspace``; must happen before its first query."""
    session.info["workspace"] = validate_workspace(workspace)
    return session


def get_session(db_url: str | None = None, workspace: str | None = None) -> Session:
    """Return a new session, bound to ``workspace`` when given."""
    session = get_session_factory(db_url)()
    if workspace is not None:
        bind_workspace(session, workspace)
    return session


@contextmanager
def session_scope(workspace: str, db_url: str | None = None) -> Iterator[Session]:
    """Workspace-bound session that commits on success, rolls back on error and always closes."""
    session = get_session(db_url, workspace=workspace)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engines() -> None:
    """Close every pooled connection (tests and shutdown)."""
    with _LOCK:
        for engine in _ENGINES.values():
            engine.dispose()
        _ENGINES.clear()
        _FACTORIES.clear()


# ── Workspace enforcement hooks ───────────────────────────────────────────────

@event.listens_for(Session, "after_begin")
def _set_workspace_setting(session, transaction, connection):
    """Expose the bound workspace to row-level security for this transaction only."""
    workspace = session.info.get("workspace")
    if workspace and connection.dialect.name == "postgresql":
        connection.execute(text("SELECT set_config('app.workspace', :ws, true)"), {"ws": workspace})


@event.listens_for(Session, "before_flush")
def _stamp_workspace(session, flush_context, instances):
    """New rows always belong to the session's bound workspace."""
    workspace = session.info.get("workspace")
    if not workspace:
        return
    for obj in session.new:
        if hasattr(obj, "workspace"):
            obj.workspace = workspace


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db(db_url: str | None = None) -> None:
    """Create or migrate the schema. Needs the database owner role on PostgreSQL."""
    from app.db.migrations import run_migrations  # noqa: PLC0415

    run_migrations(get_engine(db_url))
    logger.info("Database initialized.")


def check_db_ready(db_url: str | None = None) -> None:
    """Verify the schema is migrated (PostgreSQL) or create it (SQLite dev/test URLs)."""
    engine = get_engine(db_url)
    if not is_postgres(engine):
        Base.metadata.create_all(engine)
        return
    from app.db.migrations import assert_schema_current  # noqa: PLC0415

    assert_schema_current(engine)
