"""Render every dashboard page in English and Hebrew with Streamlit's AppTest (SQLite, TF-IDF)."""
import pytest
from streamlit.testing.v1 import AppTest

VIEWS = ["dashboard", "tracker", "decision_console", "classic_jobs", "analytics", "weekly_review", "profile",
         "analyze_job", "knowledge_base", "career_qa", "help_center"]


def _page(view: str, lang: str):
    import importlib
    import streamlit as st
    from dashboard.ui.context import close_run_session

    st.session_state["auth"] = {"username": "tester", "workspace": "demo"}
    st.session_state["lang"] = lang
    st.session_state.setdefault("_pages", {})
    try:
        importlib.import_module(f"dashboard.views.{view}").render()
    finally:
        close_run_session()


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    import os
    from app.collectors.mock_collector import MockCollector
    from app.db.session import check_db_ready, dispose_engines, session_scope
    from app.services.job_service import JobService

    url = f"sqlite:///{tmp_path_factory.mktemp('ui') / 'ui.db'}"
    old = {k: os.environ.get(k) for k in ("DATABASE_URL", "SEARCH_BACKEND")}
    os.environ["DATABASE_URL"], os.environ["SEARCH_BACKEND"] = url, "tfidf"
    check_db_ready(url)
    with session_scope("demo", url) as s:
        svc = JobService(s)
        svc.run_collectors([MockCollector()])
        svc.score_all_unscored()
        svc.career_score_all_unscored()
    import datetime as dt
    from app.db.models import Application
    from app.tracker import service as tracker
    with session_scope("demo", url) as s:
        today = tracker.local_today()
        for i, status in enumerate(["submitted", "interview", "offer", "rejected", "screening"]):
            tracker.create(s, {"company": f"Co {i}", "title": "Engineer", "status": status, "track": "devops_cloud",
                               "source": "linkedin", "submitted_date": today - dt.timedelta(days=7 * i)})
        s.flush()
        stale = s.query(Application).filter_by(status="screening").one()
        stale.last_update_at = stale.last_update_at - dt.timedelta(days=20)
    yield url
    dispose_engines()
    for k, v in old.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


@pytest.mark.parametrize("lang", ["en", "he"])
@pytest.mark.parametrize("view", VIEWS)
def test_page_renders_without_exceptions(seeded_db, view, lang):
    at = AppTest.from_function(_page, args=(view, lang), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title, "page has no title"
