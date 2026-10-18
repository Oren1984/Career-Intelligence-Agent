"""PostgreSQL integration fixtures.

Set TEST_PG_ADMIN_URL to a superuser URL of a disposable PostgreSQL+pgvector
server, e.g. postgresql+psycopg://test:test@127.0.0.1:55432/postgres
Each test session creates its own throwaway database and application role and
drops both afterwards; no existing database is touched.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL", "")

pytestmark = pytest.mark.postgres


def pytest_collection_modifyitems(config, items):
    if ADMIN_URL:
        return
    skip = pytest.mark.skip(reason="TEST_PG_ADMIN_URL not set (PostgreSQL integration tests)")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def pg_urls():
    """Create a throwaway database + app role; yield (owner_url, app_url)."""
    from app.db.migrations import run_migrations
    from app.db.session import dispose_engines, get_engine

    suffix = uuid.uuid4().hex[:8]
    db_name, role = f"cia_test_{suffix}", f"cia_test_app_{suffix}"
    password = "t3st:p%ss'" + suffix   # exercises quoting in role setup
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    base = make_url(ADMIN_URL)
    owner_url = base.set(database=db_name).render_as_string(hide_password=False)
    app_url = base.set(database=db_name, username=role, password=password).render_as_string(hide_password=False)

    old = {k: os.environ.get(k) for k in ("APP_DB_USER", "APP_DB_PASSWORD")}
    os.environ["APP_DB_USER"], os.environ["APP_DB_PASSWORD"] = role, password
    try:
        run_migrations(get_engine(owner_url))
        yield owner_url, app_url
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        dispose_engines()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
            conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()


@pytest.fixture
def app_url(pg_urls):
    """App-role URL with all workspace tables emptied before each test."""
    owner_url, url = pg_urls
    from app.db.models import WORKSPACE_TABLES
    from app.db.session import get_engine

    with get_engine(owner_url).begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(WORKSPACE_TABLES) + " RESTART IDENTITY CASCADE"))
    return url


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder (384-d, L2-normalised)."""

    model_id = "fake"
    dimension = 384

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * 384
        for tok in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 384] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_passages(self, texts):
        self.calls += 1
        if self.fail:
            raise RuntimeError("simulated embedding failure")
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        if self.fail:
            raise RuntimeError("simulated embedding failure")
        return self._vec(text)
