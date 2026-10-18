"""Reusable UI pieces: page header, KPI row, badges, empty states, footer, help links."""
from __future__ import annotations

import html
from typing import Iterable, Optional

import streamlit as st

from dashboard.ui.context import t

APP_VERSION = "2.0"
FOOTER_TEXT = "Developed and built by Oren - V2.0"   # shown verbatim on every page and the login screen

LABEL_COLORS = {
    "Apply Now": "#1a7f37",
    "Apply After Small Fix": "#0969da",
    "Stretch Opportunity": "#9a6700",
    "Good Role, Wrong Timing": "#cf222e",
    "Good Company, Wrong Role": "#8250df",
    "Not Worth It": "#6e7781",
    "Market Signal Only": "#953800",
}
LABEL_ICONS = {
    "Apply Now": "🟢", "Apply After Small Fix": "🔵", "Stretch Opportunity": "🟡",
    "Good Role, Wrong Timing": "🔴", "Good Company, Wrong Role": "🟣", "Not Worth It": "⚫",
    "Market Signal Only": "🟠", "Not Yet Scored": "⚪",
}
LABEL_KEYS = {
    "Apply Now": "apply_now", "Apply After Small Fix": "apply_after_fix",
    "Stretch Opportunity": "stretch", "Good Role, Wrong Timing": "wrong_timing",
    "Good Company, Wrong Role": "wrong_role", "Not Worth It": "not_worth_it",
    "Market Signal Only": "market_signal", "Not Yet Scored": "not_scored",
}


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def label_text(label: str) -> str:
    """Display text for a recommendation label produced by the scoring engine."""
    key = LABEL_KEYS.get(label)
    return t(f"labels.{key}") if key else label


def label_badge(label: str) -> str:
    color = LABEL_COLORS.get(label, "#6e7781")
    icon = LABEL_ICONS.get(label, "⚪")
    return f'<span class="cia-badge" style="background:{color}">{icon} {esc(label_text(label))}</span>'


def badge(text: str, color: str) -> str:
    return f'<span class="cia-badge" style="background:{color}">{esc(text)}</span>'


def page_header(title_key: str, subtitle_key: Optional[str] = None, help_topic: Optional[str] = None) -> None:
    cols = st.columns([6, 1]) if help_topic else [st.container()]
    with cols[0]:
        st.title(t(title_key))
    if help_topic:
        with cols[1]:
            help_link(help_topic)
    if subtitle_key:
        st.markdown(f'<p class="cia-subtitle">{esc(t(subtitle_key))}</p>', unsafe_allow_html=True)


def help_link(topic: str) -> None:
    """Contextual link to a Help Center section."""
    if st.button(t("common.help"), key=f"help_{topic}", icon="❓", use_container_width=True):
        st.session_state["help_topic"] = topic
        st.switch_page(st.session_state["_pages"]["help"])


def kpi_row(items: Iterable[tuple[str, object]], columns: int | None = None) -> None:
    """Row of KPI cards: [(label, value), ...]."""
    items = list(items)
    cols = st.columns(columns or len(items))
    for i, (label, value) in enumerate(items):
        with cols[i % len(cols)]:
            with st.container(border=True):
                st.metric(label, value)


def empty_state(message: str, icon: str = "ℹ️") -> None:
    st.info(message, icon=icon)


def section(title: str) -> None:
    st.subheader(title, divider="gray")


def footer() -> None:
    st.markdown(f'<div class="cia-footer">{esc(FOOTER_TEXT)}</div>', unsafe_allow_html=True)


def score_bar(score: float, max_val: float = 10.0) -> str:
    pct = max(0, min(100, int(score / max_val * 100)))
    color = "#1a7f37" if pct >= 70 else ("#9a6700" if pct >= 45 else "#cf222e")
    return (
        '<div class="cia-ltr" style="width:100%;background:rgba(128,128,128,.18);border-radius:6px;height:10px;">'
        f'<div style="background:{color};width:{pct}%;height:10px;border-radius:6px;"></div></div>'
    )
