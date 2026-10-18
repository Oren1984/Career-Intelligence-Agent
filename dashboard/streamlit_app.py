# dashboard/streamlit_app.py
# Career Intelligence Agent — Streamlit entry point (V2.0)

"""Career Intelligence Agent — Streamlit application.

Entry point only: page config, theme, authentication gate, navigation,
sidebar controls and footer. Each page lives in dashboard/views/.
Pages are registered through st.navigation, so they can only run through
this script (after the authentication gate), never as standalone URLs.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from dashboard.i18n import LANGUAGES  # noqa: E402
from dashboard.ui.auth_session import enforce_timeout, is_authenticated, save_language, sign_out  # noqa: E402
from dashboard.ui.components import footer  # noqa: E402
from dashboard.ui.context import AUTH_KEY, LANG_KEY, close_run_session, lang, t, username  # noqa: E402
from dashboard.ui.theme import apply_theme  # noqa: E402
from dashboard.views import (  # noqa: E402
    analytics, analyze_job, career_qa, classic_jobs, decision_console, help_center,
    knowledge_base, login, profile, weekly_review,
)
from dashboard.views.analyze_job import EXEC_MODES  # noqa: E402

logger = logging.getLogger(__name__)

PAGE_PATHS = ("decision", "jobs", "analytics", "weekly-review", "analyze", "knowledge-base",
              "career-qa", "profile", "help")

st.set_page_config(page_title="Career Intelligence Agent", page_icon="🎯", layout="wide")
st.session_state.setdefault(LANG_KEY, "en")


def _pages() -> dict:
    pages = {
        "decision": st.Page(decision_console.render, title=t("nav.decision"), icon="🎯", url_path="decision", default=True),
        "classic": st.Page(classic_jobs.render, title=t("nav.classic"), icon="📋", url_path="jobs"),
        "analytics": st.Page(analytics.render, title=t("nav.analytics"), icon="📊", url_path="analytics"),
        "review": st.Page(weekly_review.render, title=t("nav.review"), icon="🗓️", url_path="weekly-review"),
        "analyze": st.Page(analyze_job.render, title=t("nav.analyze"), icon="🔍", url_path="analyze"),
        "kb": st.Page(knowledge_base.render, title=t("nav.kb"), icon="📚", url_path="knowledge-base"),
        "qa": st.Page(career_qa.render, title=t("nav.qa"), icon="💬", url_path="career-qa"),
        "profile": st.Page(profile.render, title=t("nav.profile"), icon="👤", url_path="profile"),
        "help": st.Page(help_center.render, title=t("nav.help"), icon="❓", url_path="help"),
    }
    st.session_state["_pages"] = pages
    return pages


def _sidebar() -> None:
    with st.sidebar:
        st.markdown(f"### 🎯 {t('app.name')}")
        st.caption(t("sidebar.signed_in_as", user=username()) + " · "
                   + f"{t('sidebar.workspace')}: **{t('workspace.' + st.session_state[AUTH_KEY]['workspace'])}**")
        st.selectbox(
            t("sidebar.language"), list(LANGUAGES), key=LANG_KEY, format_func=lambda code: LANGUAGES[code],
            on_change=save_language,
        )
        st.radio(
            t("sidebar.exec_mode"), EXEC_MODES, key="exec_mode",
            format_func=lambda m: t(f"exec.{m}"), help=t("sidebar.exec_help"),
        )
        if st.button(t("sidebar.logout"), icon="🚪", use_container_width=True):
            sign_out()
            st.rerun()


def main() -> None:
    enforce_timeout()
    if not is_authenticated():
        apply_theme(lang())
        # Signed out: every URL (including bookmarked page URLs) renders the login form and no
        # app page or navigation link exists. After sign-in the same URL opens the real page.
        gate = st.navigation(
            [st.Page(login.render, title=t("login.submit"), icon="🔐", url_path="login", default=True)]
            + [st.Page(lambda: login.render(), title=t("login.submit"), url_path=path) for path in PAGE_PATHS],
            position="hidden",
        )
        try:
            gate.run()
        finally:
            close_run_session()
            footer()
        return

    apply_theme(lang())
    p = _pages()
    nav = st.navigation({
        t("nav.group_jobs"): [p["decision"], p["classic"], p["analytics"], p["review"]],
        t("nav.group_knowledge"): [p["analyze"], p["kb"], p["qa"], p["profile"]],
        t("nav.group_support"): [p["help"]],
    })
    _sidebar()
    try:
        nav.run()
    finally:
        close_run_session()
        footer()


main()
