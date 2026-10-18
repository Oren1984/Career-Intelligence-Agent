"""Classic Jobs — V1 keyword + semantic scoring view (preserved), as a selectable table."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.services.job_service import VALID_STATUSES
from dashboard.ui.components import empty_state, page_header, section
from dashboard.ui.context import job_service, t
from dashboard.views.jobs_common import job_filters, level_text, pipeline_actions, status_text

_LEVEL_ICON = {"high": "🟢", "medium": "🟡", "low": "🔴", "unscored": "⚪"}


def render() -> None:
    page_header("classic.title", "classic.subtitle", help_topic="jobs")
    service = job_service()

    top = st.columns([3, 1])
    with top[1]:
        pipeline_actions()
    by_source = service.get_source_analytics().get("by_source", {})
    if by_source:
        with top[0]:
            st.caption(t("classic.sources") + ": " + ", ".join(
                f"{src} ({cnt})" for src, cnt in sorted(by_source.items(), key=lambda x: -x[1])))

    f = job_filters(show_label=False, show_level=True, show_min_fit=False)
    try:
        jobs = service.get_jobs_with_scores(
            status_filter=f["status"], match_level_filter=f["level"], text_search=f["search"],
        )
    except Exception as exc:
        st.error(t("common.load_failed", error=exc))
        jobs = []

    if not jobs:
        empty_state(t("classic.empty"))
        return

    st.caption(t("classic.count", n=len(jobs)))
    df = pd.DataFrame([{
        "id": j["id"],
        t("classic.col_title"): j["title"],
        t("classic.col_company"): j["company"],
        t("classic.col_location"): j["location"],
        t("classic.col_score"): round(j["match_score"], 1),
        t("classic.col_semantic"): None if j.get("semantic_score") is None else round(j["semantic_score"], 1),
        t("classic.col_level"): f"{_LEVEL_ICON.get(j['match_level'], '⚪')} {level_text(j['match_level'])}",
        t("classic.col_status"): status_text(j["status"]),
    } for j in jobs])
    event = st.dataframe(
        df, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
        column_config={"id": None}, key="classic_table",
    )
    st.caption(t("classic.select_hint"))
    rows = event.selection.rows if event and event.selection else []
    if rows:
        selected = int(df.iloc[rows[0]]["id"])
        detail = next((j for j in jobs if j["id"] == selected), None)
        if detail:
            _detail(detail)


def _detail(detail: dict) -> None:
    jid = detail["id"]
    section(t("classic.detail", title=detail["title"]))
    d1, d2 = st.columns([2, 1])
    with d1:
        st.markdown(f"**{t('classic.col_company')}:** {detail['company']}")
        st.markdown(f"**{t('classic.col_location')}:** {detail['location']}")
        st.markdown(f"**{t('classic.source')}:** {detail['source']}")
        if detail["url"]:
            st.link_button(t("decision.view_posting"), detail["url"])
        st.text_area("description", value=detail["description"], height=200, disabled=True,
                     label_visibility="collapsed", key=f"cdesc_{jid}")
    with d2:
        final = detail.get("final_score") or detail["match_score"]
        st.markdown(f"### {_LEVEL_ICON.get(detail['match_level'], '⚪')} {final:.1f} — {level_text(detail['match_level'])}")
        if detail.get("keyword_score") is not None and detail.get("semantic_score") is not None:
            s1, s2 = st.columns(2)
            s1.metric(t("classic.keyword"), f"{detail['keyword_score']:.1f}")
            s2.metric(t("classic.col_semantic"), f"{detail['semantic_score']:.1f}/10")
        if detail.get("matched_themes"):
            st.success(", ".join(detail["matched_themes"]))
        if detail["matched_keywords"]:
            st.markdown(f"**{t('classic.matched')}:**")
            st.success(", ".join(detail["matched_keywords"]))
        if detail["missing_keywords"]:
            st.info(", ".join(detail["missing_keywords"]))
        if detail["rejection_flags"]:
            st.warning(", ".join(detail["rejection_flags"]))
        st.write(detail["explanation"])

        statuses = sorted(VALID_STATUSES)
        new_status = st.selectbox(
            t("filters.status"), statuses, key=f"status_select_{jid}", format_func=status_text,
            index=statuses.index(detail["status"]) if detail["status"] in statuses else 0,
        )
        if st.button(t("common.save"), key=f"save_{jid}", type="primary"):
            if job_service().update_status(jid, new_status):
                st.toast(t("decision.status_saved", status=status_text(new_status)), icon="✅")
                st.rerun()
            st.error(t("common.save_failed"))
