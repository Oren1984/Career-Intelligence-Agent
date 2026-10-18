"""Analytics — job pipeline statistics (sources, match levels, labels, feedback)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.ui import charts
from dashboard.ui.components import empty_state, kpi_row, label_text, page_header, section
from dashboard.ui.context import job_service, t
from dashboard.views.jobs_common import level_text


def render() -> None:
    page_header("analytics.title", "analytics.subtitle")
    service = job_service()
    try:
        analytics = service.get_source_analytics()
        career = service.get_career_summary_stats()
    except Exception as exc:
        st.error(t("common.load_failed", error=exc))
        return

    kpi_row([
        (t("kpi.total_jobs"), analytics["total_jobs"]),
        (t("kpi.classic_scored"), analytics["total_scored"]),
        (t("kpi.career_scored"), career.get("career_scored", 0)),
        (t("kpi.high_ratio"), f"{analytics['high_match_ratio'] * 100:.0f}%"),
    ])
    if not analytics["total_jobs"]:
        empty_state(t("analytics.empty"))
        return

    col_a, col_b = st.columns(2)
    with col_a:
        section(t("analytics.by_label"))
        labels = {k: v for k, v in career.get("label_counts", {}).items() if v > 0}
        charts.bar(pd.DataFrame({t("common.category"): [label_text(k) for k in labels],
                                 t("common.count"): list(labels.values())}),
                   t("common.category"), t("common.count"), key="an_labels")
    with col_b:
        section(t("analytics.by_source"))
        src = analytics["by_source"]
        charts.bar(pd.DataFrame({t("common.category"): list(src), t("common.count"): list(src.values())}),
                   t("common.category"), t("common.count"), key="an_sources")

    col_c, col_d = st.columns(2)
    with col_c:
        section(t("analytics.by_level"))
        lv = analytics["by_level"]
        charts.bar(pd.DataFrame({t("common.category"): [level_text(k) for k in lv],
                                 t("common.count"): list(lv.values())}),
                   t("common.category"), t("common.count"), key="an_levels")
    with col_d:
        section(t("analytics.feedback"))
        fb = service.get_feedback_summary()
        charts.bar(pd.DataFrame({t("common.category"): [t(f"feedback.{k}") for k in fb],
                                 t("common.count"): list(fb.values())}),
                   t("common.category"), t("common.count"), key="an_feedback")
