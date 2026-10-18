"""Tracker editor save logic (add / edit / delete / validation) run inside a Streamlit script context."""
import datetime as dt

import pytest
from streamlit.testing.v1 import AppTest


def _save_script(mode: str):
    import datetime as dt
    import pandas as pd
    import streamlit as st
    from app.tracker import service
    from dashboard.ui.context import close_run_session, db
    from dashboard.views import tracker as view

    st.session_state["auth"] = {"username": "t", "workspace": "demo"}
    st.session_state["lang"] = "en"
    if st.session_state.get("done"):   # _save() reruns the script after a successful save
        return
    st.session_state["done"] = True
    try:
        apps = service.list_applications(db())
        original = view._frame(apps, dt.date(2026, 10, 18))
        edited = original.copy()
        if mode == "edit_add_delete":
            edited.loc[edited["company"] == "Keep", "status"] = "Professional interview"
            edited = edited[edited["company"] != "Remove"]
            edited = pd.concat([edited, pd.DataFrame([{"id": None, "company": "New Co", "title": "SRE",
                                                       "status": "Submitted", "submitted_date": dt.date(2026, 10, 1)}])],
                               ignore_index=True)
        elif mode == "invalid":
            edited.loc[edited["company"] == "Keep", "company"] = ""
            edited = edited[edited["company"] != "Remove"]
        view._save(original, edited)
    finally:
        close_run_session()


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    from app.db.session import check_db_ready, dispose_engines, session_scope
    from app.tracker import service

    url = f"sqlite:///{tmp_path / 't.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    check_db_ready(url)
    with session_scope("demo", url) as s:
        for name in ("Keep", "Remove"):
            service.create(s, {"company": name, "title": "Engineer", "status": "submitted"})
    yield url
    dispose_engines()


def _rows(url):
    from app.db.session import session_scope
    from app.tracker import service
    with session_scope("demo", url) as s:
        return {a.company: (a.status, a.row_uid) for a in service.list_applications(s)}


def test_editor_save_adds_updates_and_deletes(seeded):
    before = _rows(seeded)
    at = AppTest.from_function(_save_script, args=("edit_add_delete",), default_timeout=60).run()
    assert not at.exception
    after = _rows(seeded)
    assert set(after) == {"Keep", "New Co"}
    assert after["Keep"][0] == "interview"
    assert after["Keep"][1] == before["Keep"][1]          # stable row identifier
    assert after["New Co"][0] == "submitted"


def test_editor_rejects_invalid_batch_atomically(seeded):
    at = AppTest.from_function(_save_script, args=("invalid",), default_timeout=60).run()
    assert at.error and "required" in at.error[0].value
    assert set(_rows(seeded)) == {"Keep", "Remove"}       # nothing deleted or changed
