# scripts/init_db.py
# Create or migrate the database schema (run with the database owner credentials).

"""Initialize or migrate the database schema.

Uses ``MIGRATION_DATABASE_URL`` (owner role) when set, otherwise ``DATABASE_URL``.
On PostgreSQL this also enables pgvector, applies row-level security and
creates the least-privilege application role from APP_DB_USER/APP_DB_PASSWORD.
Idempotent — safe to run on every deployment.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from sqlalchemy import inspect  # noqa: E402

from app.db.migrations import apply_legacy_score_columns, run_migrations  # noqa: E402
from app.db.session import get_engine  # noqa: E402


def apply_v2_migrations(engine):
    """Add V2 columns to the scores table if they are absent (safe, idempotent)."""
    if "scores" not in inspect(engine).get_table_names():
        return
    with engine.connect() as conn:
        apply_legacy_score_columns(conn)
        conn.commit()


if __name__ == "__main__":
    engine = get_engine(os.environ.get("MIGRATION_DATABASE_URL") or None)
    run_migrations(engine)
    logger.info("Database schema is current (%s).", engine.url.render_as_string(hide_password=True))
    print("Database initialized successfully.")
