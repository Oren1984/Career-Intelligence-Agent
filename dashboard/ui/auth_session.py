"""Login state in Streamlit: sign-in, sign-out, inactivity timeout, language preference.

Session mechanism: the authenticated record lives in Streamlit's server-side
session state for one browser connection. There is no cookie or token, so a
page reload or a new tab starts a new session and asks for the password again.
Inactivity is measured between interactions (Streamlit only runs code when the
user interacts), so an idle tab is logged out on its next interaction.
"""
from __future__ import annotations

import logging
import time

import streamlit as st

from app.auth import User, session_timeout_minutes
from app.db.models import UserPreference
from dashboard.i18n import normalize_language
from dashboard.ui.context import AUTH_KEY, LANG_KEY, close_run_session, db, session_factory
from app.db.session import bind_workspace

logger = logging.getLogger(__name__)

FLASH_KEY = "_flash"
LANG_TOUCHED_KEY = "_lang_touched"


def is_authenticated() -> bool:
    return bool(st.session_state.get(AUTH_KEY))


def sign_in(user: User) -> None:
    """Start a fresh session for ``user`` (no state carries over from before login)."""
    chosen_lang = st.session_state.get(LANG_KEY) if st.session_state.get(LANG_TOUCHED_KEY) else None
    _reset_state()
    now = time.time()
    st.session_state[AUTH_KEY] = {
        "username": user.username, "workspace": user.workspace, "login_at": now, "last_activity": now,
    }
    if chosen_lang:
        st.session_state[LANG_KEY] = chosen_lang
        save_language()
    else:
        st.session_state[LANG_KEY] = _stored_language(user) or "en"
    logger.info("User '%s' signed in (workspace %s).", user.username, user.workspace)


def sign_out(reason: str = "logged_out") -> None:
    """Clear everything belonging to the session; keep only the UI language and a notice."""
    lang = st.session_state.get(LANG_KEY, "en")
    username = (st.session_state.get(AUTH_KEY) or {}).get("username")
    close_run_session()
    _reset_state()
    st.session_state[LANG_KEY] = lang
    st.session_state[FLASH_KEY] = reason
    if username:
        logger.info("User '%s' signed out (%s).", username, reason)


def enforce_timeout() -> bool:
    """Sign out if idle longer than the configured timeout; returns True if it did."""
    record = st.session_state.get(AUTH_KEY)
    if not record:
        return False
    now = time.time()
    if now - record.get("last_activity", now) > session_timeout_minutes() * 60:
        sign_out("expired")
        return True
    record["last_activity"] = now
    return False


def _reset_state() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def _stored_language(user: User) -> str | None:
    session = bind_workspace(session_factory()(), user.workspace)
    try:
        pref = session.query(UserPreference).filter_by(username=user.username).first()
        return normalize_language(pref.language) if pref else None
    except Exception as exc:
        logger.warning("Could not read language preference: %s", exc)
        return None
    finally:
        session.close()


def save_language() -> None:
    """Persist the current language for the signed-in user (on_change callback)."""
    st.session_state[LANG_TOUCHED_KEY] = True
    record = st.session_state.get(AUTH_KEY)
    if not record:
        return
    lang = normalize_language(st.session_state.get(LANG_KEY))
    session = db()
    try:
        pref = session.query(UserPreference).filter_by(username=record["username"]).first()
        if pref is None:
            session.add(UserPreference(username=record["username"], language=lang))
        else:
            pref.language = lang
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("Could not save language preference: %s", exc)
