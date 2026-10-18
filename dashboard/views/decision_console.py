"""Decision Console — career-scored jobs with the full decision detail panel."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.db.models import VALID_FEEDBACK_SIGNALS
from app.services.job_service import VALID_STATUSES
from dashboard.ui.components import LABEL_ICONS, empty_state, esc, kpi_row, label_badge, page_header, section
from dashboard.ui.context import job_service, t
from dashboard.views.jobs_common import job_filters, pipeline_actions, status_text

_FEEDBACK = ["liked", "applied", "not_interested", "too_senior", "wrong_direction", "irrelevant"]
assert set(_FEEDBACK) <= VALID_FEEDBACK_SIGNALS


def render() -> None:
    page_header("decision.title", "decision.subtitle", help_topic="jobs")
    service = job_service()
    summary = service.get_summary_stats()
    career = service.get_career_summary_stats()
    labels = career.get("label_counts", {})
    kpi_row([
        (t("kpi.total_jobs"), summary["total_jobs"]),
        (t("kpi.career_scored"), career.get("career_scored", 0)),
        (t("labels.apply_now"), labels.get("Apply Now", 0)),
        (t("labels.apply_after_fix"), labels.get("Apply After Small Fix", 0)),
        (t("kpi.avg_fit"), f"{career.get('avg_fit_score', 0):.0f}/100"),
        (t("kpi.unreviewed"), summary["status_counts"].get("new", 0)),
    ], columns=6)

    top = st.columns([3, 1])
    with top[1]:
        pipeline_actions()
    f = job_filters()

    try:
        jobs = service.get_jobs_with_career_scores(
            status_filter=f["status"], label_filter=f["label"], min_fit_score=f["min_fit"], text_search=f["search"],
        )
    except Exception as exc:
        st.error(t("common.load_failed", error=exc))
        jobs = []

    if not jobs:
        empty_state(t("decision.empty"))
        return

    st.caption(t("decision.count", n=len(jobs)))
    for job in jobs:
        jid = job["id"]
        fit = job.get("overall_fit_score")
        label = job.get("recommendation_label", "Not Yet Scored")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([5, 3, 1.3, 1.2], vertical_alignment="center")
            c1.markdown(f"**{esc(job['title'])}** — {esc(job['company'])}", unsafe_allow_html=True)
            c1.caption(f"{job.get('location', '')} · {job.get('source', '')}")
            c2.markdown(label_badge(label), unsafe_allow_html=True)
            c3.markdown(f"**{fit:.0f}**/100" if fit is not None else "—")
            if c4.button(t("common.details"), key=f"cd_{jid}", use_container_width=True):
                st.session_state["career_selected_id"] = jid

    sel_id = st.session_state.get("career_selected_id")
    if sel_id:
        detail = next((j for j in jobs if j["id"] == sel_id), None)
        if detail is None:
            detail = next((j for j in service.get_jobs_with_career_scores() if j["id"] == sel_id), None)
        if detail:
            _detail(detail)


def _detail(detail: dict) -> None:
    sel_id = detail["id"]
    label = detail.get("recommendation_label", "Not Yet Scored")
    fit = detail.get("overall_fit_score") or 0
    section(f"{LABEL_ICONS.get(label, '')} {detail['title']}")
    st.markdown(label_badge(label), unsafe_allow_html=True)
    st.caption(f"{detail['company']} · {detail.get('location', '')} · {t('decision.fit')}: {fit:.0f}/100")
    if detail.get("recommendation_reason"):
        st.info(detail["recommendation_reason"])

    col_a, col_b = st.columns([3, 2])
    with col_a:
        breakdown = detail.get("score_breakdown", {})
        if breakdown:
            st.markdown(f"#### {t('decision.breakdown')}")
            st.dataframe(pd.DataFrame({
                t("decision.dimension"): [d.replace("_", " ").title() for d in breakdown],
                t("decision.score_0_10"): [round(v, 1) for v in breakdown.values()],
            }), hide_index=True, use_container_width=True)
        for key, items, fn, prefix in (
            ("decision.strengths", detail.get("strengths", []), st.success, "✓"),
            ("decision.gaps", detail.get("gaps", []), st.warning, "△"),
            ("decision.risks", detail.get("risks", []), st.error, "⚠"),
        ):
            if items:
                st.markdown(f"#### {t(key)}")
                for item in items:
                    fn(f"{prefix} {item}")
        st.markdown(f"#### {t('decision.description')}")
        st.text_area("desc", value=detail.get("description", ""), height=180, disabled=True,
                     label_visibility="collapsed", key=f"desc_{sel_id}")

    with col_b:
        st.markdown(f"#### {t('decision.intelligence')}")
        m = st.columns(3)
        m[0].metric(t("decision.seniority"), detail.get("detected_seniority", "?"))
        m[1].metric(t("decision.work_mode"), detail.get("detected_work_mode", "?"))
        m[2].metric(t("decision.direction"), detail.get("career_direction_alignment", "?"))
        if detail.get("detected_domain"):
            st.caption(f"{t('decision.domain')}: **{detail['detected_domain']}**")
        if detail.get("best_matching_project"):
            st.markdown(f"#### {t('decision.portfolio')}")
            st.success(t("decision.lead_with", project=detail["best_matching_project"]))
            for h in detail.get("portfolio_highlights") or []:
                st.caption(f"• {h}")
        severity = detail.get("gap_severity", "")
        if severity:
            icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(severity, "")
            st.markdown(f"#### {t('decision.gap_severity')}: {icon} {severity.upper()}")
        if detail.get("easy_to_close_gaps"):
            st.caption(f"{t('decision.easy_gaps')}: {', '.join(detail['easy_to_close_gaps'][:4])}")
        if detail.get("hard_to_close_gaps"):
            st.caption(f"{t('decision.hard_gaps')}: {', '.join(detail['hard_to_close_gaps'][:3])}")
        if detail.get("action_items"):
            st.markdown(f"#### {t('decision.actions')}")
            for i, item in enumerate(detail["action_items"], 1):
                st.markdown(f"**{i}.** {item}")
        if detail.get("url"):
            st.link_button(t("decision.view_posting"), detail["url"])

        st.divider()
        st.markdown(f"#### {t('decision.feedback')}")
        fb = st.columns(3)
        for i, sig in enumerate(_FEEDBACK):
            if fb[i % 3].button(t(f"feedback.{sig}"), key=f"fb_{sel_id}_{sig}", use_container_width=True):
                if job_service().record_feedback(sel_id, sig):
                    st.toast(t("decision.feedback_saved", signal=t(f"feedback.{sig}")), icon="✅")
                else:
                    st.error(t("common.save_failed"))

        st.markdown(f"#### {t('decision.update_status')}")
        statuses = sorted(VALID_STATUSES)
        new_status = st.selectbox(
            t("filters.status"), statuses, key=f"cs_status_{sel_id}", format_func=status_text,
            index=statuses.index(detail["status"]) if detail["status"] in statuses else 0,
        )
        b1, b2 = st.columns(2)
        if b1.button(t("common.save"), key=f"cs_save_{sel_id}", type="primary", use_container_width=True):
            if job_service().update_status(sel_id, new_status):
                st.toast(t("decision.status_saved", status=status_text(new_status)), icon="✅")
                st.rerun()
            st.error(t("common.save_failed"))
        if b2.button(t("common.close"), key=f"cs_close_{sel_id}", use_container_width=True):
            st.session_state.pop("career_selected_id", None)
            st.rerun()
