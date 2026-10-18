"""Login screen (username + password). Rendered instead of the app until sign-in."""
from __future__ import annotations

import math

import streamlit as st

from app.auth import authenticate
from dashboard.i18n import LANGUAGES
from dashboard.ui.auth_session import FLASH_KEY, LANG_TOUCHED_KEY, sign_in
from dashboard.ui.components import esc
from dashboard.ui.context import LANG_KEY, t


def _mark_lang_touched() -> None:
    st.session_state[LANG_TOUCHED_KEY] = True


def render() -> None:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.markdown(f"# 🎯 {esc(t('app.name'))}")
        st.markdown(f'<p class="cia-subtitle">{esc(t("login.subtitle"))}</p>', unsafe_allow_html=True)

        flash = st.session_state.pop(FLASH_KEY, None)
        if flash == "expired":
            st.warning(t("login.expired"), icon="⏱️")
        elif flash == "logged_out":
            st.success(t("login.logged_out"), icon="👋")

        st.selectbox(t("sidebar.language"), list(LANGUAGES), key=LANG_KEY,
                     format_func=lambda code: LANGUAGES[code], on_change=_mark_lang_touched)

        with st.form("login_form", border=True):
            username = st.text_input(t("login.username"), autocomplete="username")
            password = st.text_input(t("login.password"), type="password", autocomplete="current-password")
            submitted = st.form_submit_button(t("login.submit"), type="primary", use_container_width=True)

        if submitted:
            result = authenticate(username, password)
            if result.reason == "ok":
                sign_in(result.user)
                st.rerun()
            elif result.reason == "locked":
                st.error(t("login.locked", minutes=max(1, math.ceil(result.retry_after / 60))), icon="🔒")
            elif result.reason == "no_users":
                st.error(t("login.no_users"), icon="⚙️")
            else:
                st.error(t("login.invalid"), icon="🚫")
        st.caption(t("login.privacy"))
