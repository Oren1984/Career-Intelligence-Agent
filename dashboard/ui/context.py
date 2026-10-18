"""Per-run application context: authenticated workspace, language, DB session, services.

The workspace always comes from the server-side authenticated session record
(``st.session_state["auth"]``), never from query parameters or widgets.
Every cached resource that holds workspace data is keyed by workspace (and database URL).
"""
from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from app.db.session import bind_workspace, check_db_ready, database_url, get_session_factory
from app.services.job_service import JobService
from app.services.workspace_profile import candidate_profile_for, scoring_profile_for
from dashboard.i18n import normalize_language, translate

logger = logging.getLogger(__name__)

AUTH_KEY = "auth"
LANG_KEY = "lang"
_SESSION_KEY = "_db_session"


class NotAuthenticated(RuntimeError):
    """Raised when page code runs without an authenticated session."""


# ── Language ────────────────────────────────────────────────────────────────

def lang() -> str:
    return normalize_language(st.session_state.get(LANG_KEY))


def t(key: str, **params: Any) -> str:
    return translate(lang(), key, **params)


# ── Identity ────────────────────────────────────────────────────────────────

def auth() -> dict:
    record = st.session_state.get(AUTH_KEY)
    if not record:
        raise NotAuthenticated("No authenticated session.")
    return record


def workspace() -> str:
    return auth()["workspace"]


def username() -> str:
    return auth()["username"]


# ── Database ────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _session_factory(url: str):
    check_db_ready(url)
    return get_session_factory(url)


def session_factory():
    """Process-wide session factory per DATABASE_URL (one connection pool); schema verified once."""
    return _session_factory(database_url())


def db():
    """Workspace-bound session for the current script run (closed by close_run_session)."""
    session = st.session_state.get(_SESSION_KEY)
    if session is None:
        session = bind_workspace(session_factory()(), workspace())
        st.session_state[_SESSION_KEY] = session
    return session


def close_run_session() -> None:
    session = st.session_state.pop(_SESSION_KEY, None)
    if session is not None:
        try:
            session.rollback()
        finally:
            session.close()


# ── Workspace-scoped services (cache keys include the workspace) ────────────

@st.cache_resource(show_spinner=False, ttl=600)
def _candidate_profile(ws: str, url: str):
    session = bind_workspace(_session_factory(url)(), ws)
    try:
        return candidate_profile_for(session, ws)
    finally:
        session.close()


def candidate_profile():
    try:
        return _candidate_profile(workspace(), database_url())
    except Exception as exc:
        logger.warning("Could not load candidate profile: %s", exc)
        return None


def job_service() -> JobService:
    """JobService with the career profile (as in V1's dashboard)."""
    profile = candidate_profile()
    return JobService(db(), profile=profile.to_dict() if profile else None)


def classic_job_service() -> JobService:
    """JobService with the classic scoring profile (as in V1's scripts)."""
    return JobService(db(), profile=scoring_profile_for(workspace()))


@st.cache_resource(show_spinner=False)
def _knowledge_service(ws: str, url: str):
    from app.rag.workspace_knowledge import WorkspaceKnowledgeService  # noqa: PLC0415
    return WorkspaceKnowledgeService(_session_factory(url), ws)


def knowledge_service():
    return _knowledge_service(workspace(), database_url())


@st.cache_resource(show_spinner=False, ttl=600)
def _analyzer(ws: str, url: str):
    from app.services.rag_job_analysis import RAGJobAnalyzer  # noqa: PLC0415
    profile = _candidate_profile(ws, url)
    return RAGJobAnalyzer(profile=profile.to_dict() if profile else None,
                          knowledge_service=_knowledge_service(ws, url))


def analyzer():
    return _analyzer(workspace(), database_url())


@st.cache_resource(show_spinner=False)
def _qa_service(ws: str, url: str):
    from app.rag.qa_service import CareerQAService  # noqa: PLC0415
    return CareerQAService(knowledge_service=_knowledge_service(ws, url))


def qa_service():
    return _qa_service(workspace(), database_url())


def clear_profile_caches() -> None:
    """Call after the profile overlay changes (profile and analyzer embed it)."""
    _candidate_profile.clear()
    _analyzer.clear()
