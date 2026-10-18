"""Weekly Review — strategic summary generated from career-scored jobs."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.ui import charts
from dashboard.ui.components import LABEL_ICONS, empty_state, page_header, section
from dashboard.ui.context import job_service, t


def render() -> None:
    page_header("review.title", "review.subtitle")
    if st.button(t("review.generate"), type="primary"):
        with st.spinner(t("common.working")):
            try:
                review = job_service().generate_weekly_review()
                if not review or (not review.get("top_opportunities") and not review.get("focus_next_7_days")):
                    st.warning(t("review.not_enough"))
                else:
                    st.session_state["weekly_review"] = review
            except Exception as exc:
                st.error(t("common.load_failed", error=exc))

    review = st.session_state.get("weekly_review")
    if not review:
        empty_state(t("review.empty"))
        return

    if review.get("executive_summary"):
        st.info(review["executive_summary"])
    r1, r2 = st.columns(2)
    with r1:
        if review.get("top_opportunities"):
            section(t("review.top"))
            for opp in review["top_opportunities"]:
                st.markdown(
                    f"{LABEL_ICONS.get(opp.get('label', ''), '⚪')} **{opp['title']}** — {opp['company']} · "
                    f"{t('decision.fit')}: {opp.get('fit_score', 0):.0f}/100"
                )
        if review.get("focus_next_7_days"):
            section(t("review.focus7"))
            for item in review["focus_next_7_days"]:
                st.success(f"→ {item}")
    with r2:
        if review.get("recurring_missing_skills"):
            section(t("review.missing_skills"))
            for skill, freq in review["recurring_missing_skills"][:6]:
                st.write(t("review.skill_freq", skill=skill, n=freq))
        if review.get("focus_next_30_days"):
            section(t("review.focus30"))
            for item in review["focus_next_30_days"]:
                st.info(f"→ {item}")

    dist = {k: v for k, v in review.get("direction_distribution", {}).items() if v > 0}
    if dist:
        section(t("review.direction"))
        charts.bar(pd.DataFrame({t("common.category"): list(dist), t("common.count"): list(dist.values())}),
                   t("common.category"), t("common.count"), key="rv_direction")
    if review.get("strongest_job_direction"):
        st.success(t("review.strongest", direction=review["strongest_job_direction"]))
    if review.get("low_value_patterns"):
        section(t("review.low_value"))
        for p in review["low_value_patterns"]:
            st.warning(f"⚠ {p}")
