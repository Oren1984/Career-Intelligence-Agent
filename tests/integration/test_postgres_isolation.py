"""PostgreSQL schema, connection-pool and workspace-isolation tests (row-level security)."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.collectors.base import RawJob
from app.db.migrations import SCHEMA_VERSION, assert_schema_current, run_migrations
from app.db.models import Application, Job, Score, WORKSPACE_TABLES
from app.db.normalizer import insert_jobs_dedup
from app.db.session import get_engine, get_session, session_scope

pytestmark = pytest.mark.postgres


def _raw(title="Platform Engineer", company="Acme"):
    return RawJob(title=title, company=company, location="Remote",
                  description=f"{title} with Kubernetes", url="https://example.com/1", source="test")


# ── Schema / migrations ──────────────────────────────────────────────────────

def test_migrations_idempotent_and_rls_enabled(pg_urls):
    owner_url, _ = pg_urls
    engine = get_engine(owner_url)
    run_migrations(engine)  # second run must be a no-op
    run_migrations(engine)
    assert_schema_current(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT max(version) FROM schema_migrations")).scalar() == SCHEMA_VERSION
        rows = conn.execute(text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(:t)"
        ), {"t": list(WORKSPACE_TABLES)}).all()
        assert {r[0] for r in rows} == set(WORKSPACE_TABLES)
        assert all(r[1] and r[2] for r in rows)
        assert conn.execute(text(
            "SELECT count(*) FROM pg_indexes WHERE indexname = 'ix_knowledge_chunks_embedding_hnsw'"
        )).scalar() == 1


def test_app_role_cannot_drop_or_disable_rls(app_url):
    for statement in ("DROP TABLE jobs", "ALTER TABLE jobs DISABLE ROW LEVEL SECURITY",
                      "INSERT INTO schema_migrations (version) VALUES (999)"):
        with get_engine(app_url).connect() as conn:
            with pytest.raises((ProgrammingError, DBAPIError)):
                conn.execute(text(statement))


# ── Connection pool ──────────────────────────────────────────────────────────

def test_engine_and_pool_are_reused(app_url):
    engine = get_engine(app_url)
    assert get_engine(app_url) is engine
    pids = set()
    for _ in range(12):
        with session_scope("demo", app_url) as s:
            pids.add(s.execute(text("SELECT pg_backend_pid()")).scalar())
    assert engine.pool.checkedout() == 0
    assert len(pids) <= engine.pool.size()


def test_workspace_setting_does_not_leak_between_pooled_connections(app_url):
    with session_scope("demo", app_url) as s:
        insert_jobs_dedup(s, [_raw()])
    unbound = get_session(app_url)
    try:
        assert unbound.query(Job).count() == 0
        assert unbound.execute(text("SELECT current_setting('app.workspace', true)")).scalar() in (None, "")
    finally:
        unbound.close()


# ── Isolation ────────────────────────────────────────────────────────────────

def test_rows_are_isolated_per_workspace(app_url):
    with session_scope("demo", app_url) as s:
        insert_jobs_dedup(s, [_raw("Demo Job", "DemoCo")])
    with session_scope("personal", app_url) as s:
        insert_jobs_dedup(s, [_raw("Personal Job", "SecretCo")])
        personal_id = s.query(Job).one().id

    with session_scope("demo", app_url) as s:
        titles = [j.title for j in s.query(Job).all()]
        assert titles == ["Demo Job"]
        # Direct identifier access, update and delete of another workspace's row do nothing.
        assert s.query(Job).filter_by(id=personal_id).first() is None
        assert s.query(Job).filter_by(id=personal_id).update({"title": "hacked"}) == 0
        assert s.query(Job).filter_by(id=personal_id).delete() == 0
        assert s.execute(text("SELECT count(*) FROM jobs")).scalar() == 1

    with session_scope("personal", app_url) as s:
        assert [j.title for j in s.query(Job).all()] == ["Personal Job"]


def test_same_job_may_exist_in_both_workspaces(app_url):
    for ws in ("demo", "personal"):
        with session_scope(ws, app_url) as s:
            inserted, skipped = insert_jobs_dedup(s, [_raw()])
            assert (inserted, skipped) == (1, 0)


def test_new_rows_are_stamped_with_bound_workspace(app_url):
    with session_scope("demo", app_url) as s:
        s.add(Application(row_uid="00000000-0000-0000-0000-000000000001", company="X",
                          workspace="personal"))  # spoofed value is overridden
    with session_scope("demo", app_url) as s:
        assert s.query(Application).one().workspace == "demo"
    with session_scope("personal", app_url) as s:
        assert s.query(Application).count() == 0


def test_raw_sql_cannot_write_into_another_workspace(app_url):
    with pytest.raises((ProgrammingError, DBAPIError)):
        with session_scope("demo", app_url) as s:
            s.execute(text(
                "INSERT INTO applications (workspace, row_uid, company) "
                "VALUES ('personal', '00000000-0000-0000-0000-000000000002', 'X')"
            ))


def test_unbound_session_cannot_read_or_write(app_url):
    with session_scope("personal", app_url) as s:
        insert_jobs_dedup(s, [_raw()])
    s = get_session(app_url)
    try:
        assert s.query(Job).count() == 0
        s.add(Score(job_id=1, match_score=1.0))
        with pytest.raises((ProgrammingError, DBAPIError)):
            s.commit()
    finally:
        s.rollback()
        s.close()


def test_workspace_stamped_on_score_rows_via_job_service(app_url):
    from app.services.job_service import JobService

    with session_scope("demo", app_url) as s:
        insert_jobs_dedup(s, [_raw()])
        assert JobService(s).score_all_unscored() == 1
    with session_scope("demo", app_url) as s:
        assert s.query(Score).one().workspace == "demo"
    with session_scope("personal", app_url) as s:
        assert s.query(Score).count() == 0
