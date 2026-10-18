"""Shared job filters and the explicit job-pipeline actions (collect / score / reset)."""
from __future__ import annotations

import logging

import streamlit as st

from app.matching.career_scorer import ALL_LABELS
from app.services.job_service import VALID_STATUSES
from dashboard.ui.components import label_text
from dashboard.ui.context import classic_job_service, job_service, t, workspace

logger = logging.getLogger(__name__)

LEVELS = ["high", "medium", "low", "unscored"]
FETCH_MODES = ["mock", "rss", "israel"]


def status_text(status: str) -> str:
    return t(f"job_status.{status}") if status in VALID_STATUSES else status


def level_text(level: str) -> str:
    return t(f"levels.{level}") if level in LEVELS else level


def job_filters(show_label: bool = True, show_level: bool = False, show_min_fit: bool = True) -> dict:
    """One filter row above the content; values persist across pages in session state."""
    with st.container(border=True):
        cols = st.columns([2, 2, 2, 3] if show_min_fit or show_level else [2, 2, 3])
        i = 0
        status = cols[i].selectbox(
            t("filters.status"), ["all"] + sorted(VALID_STATUSES), key="f_status",
            format_func=lambda s: t("common.all") if s == "all" else status_text(s),
        )
        i += 1
        label = level = None
        min_fit = 0
        if show_label:
            label = cols[i].selectbox(
                t("filters.label"), ["all"] + ALL_LABELS, key="f_label",
                format_func=lambda s: t("common.all") if s == "all" else label_text(s),
            )
            i += 1
        if show_level:
            level = cols[i].selectbox(
                t("filters.level"), ["all"] + LEVELS, key="f_level",
                format_func=lambda s: t("common.all") if s == "all" else level_text(s),
            )
            i += 1
        elif show_min_fit:
            min_fit = cols[i].slider(t("filters.min_fit"), 0, 100, step=5, key="f_min_fit")
            i += 1
        search = cols[i].text_input(t("filters.search"), key="f_search", placeholder=t("filters.search_ph"))
    return {
        "status": None if status == "all" else status,
        "label": None if not label or label == "all" else label,
        "level": None if not level or level == "all" else level,
        "min_fit": min_fit or None,
        "search": search.strip() or None,
    }


def pipeline_actions() -> None:
    """Explicit collection and scoring (nothing runs automatically at startup)."""
    with st.popover(t("pipeline.title"), icon="⚙️", use_container_width=True):
        st.caption(t("pipeline.caption"))
        mode = st.selectbox(t("pipeline.source"), FETCH_MODES, key="pipe_mode",
                            format_func=lambda m: t(f"source_modes.{m}"))
        if st.button(t("pipeline.fetch"), use_container_width=True, type="primary"):
            _fetch(mode)
        c1, c2 = st.columns(2)
        if c1.button(t("pipeline.score_classic"), use_container_width=True):
            _run(lambda: classic_job_service().score_all_unscored(), "pipeline.scored_classic")
        if c2.button(t("pipeline.score_career"), use_container_width=True, help=t("pipeline.score_career_help")):
            _run(lambda: job_service().career_score_all_unscored(), "pipeline.scored_career")
        st.divider()
        confirm = st.checkbox(t("pipeline.reset_confirm"), key="pipe_reset_confirm")
        if st.button(t("pipeline.reset"), use_container_width=True, disabled=not confirm):
            _reset()


def _run(fn, done_key: str) -> None:
    with st.spinner(t("common.working")):
        try:
            n = fn()
            st.toast(t(done_key, n=n), icon="✅")
        except Exception as exc:
            logger.exception("Pipeline action failed")
            st.error(t("pipeline.failed", error=exc))
            return
    st.rerun()


def _fetch(mode: str) -> None:
    from scripts.fetch_jobs import build_collectors  # noqa: PLC0415

    with st.spinner(t("pipeline.fetching")):
        try:
            collectors = build_collectors(mode)
            if not collectors:
                st.warning(t("pipeline.no_collectors"))
                return
            stats = classic_job_service().run_collectors(collectors)
        except Exception as exc:
            logger.exception("Fetch failed")
            st.error(t("pipeline.failed", error=exc))
            return
    st.toast(t("pipeline.fetched", **stats), icon="✅")
    st.rerun()


def _reset() -> None:
    from scripts import reset_demo_state as reset  # noqa: PLC0415

    ws = workspace()
    with st.spinner(t("common.working")):
        try:
            reset.reset_database(ws)
            reset.fetch_jobs("israel", ws)
            reset.score_jobs(ws)
        except Exception as exc:
            logger.exception("Reset failed")
            st.error(t("pipeline.failed", error=exc))
            return
    st.session_state.pop("pipe_reset_confirm", None)
    st.toast(t("pipeline.reset_done"), icon="✅")
    st.rerun()
