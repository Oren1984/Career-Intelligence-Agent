"""Dashboard — job-search KPIs and charts from the application tracker (workbook definitions)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.tracker import service
from app.tracker.vocab import SOURCES, STALE_DAYS, TRACKS, label
from dashboard.ui import charts
from dashboard.ui.components import empty_state, kpi_row, page_header, section
from dashboard.ui.context import db, lang, t


def render() -> None:
    page_header("dashboard.title", "dashboard.subtitle", help_topic="dashboard")
    apps = service.list_applications(db())
    if not apps:
        empty_state(t("dashboard.empty"))
        if st.button(t("dashboard.open_tracker"), type="primary"):
            st.switch_page(st.session_state["_pages"]["tracker"])
        return

    today = service.local_today()
    dated = [a.submitted_date for a in apps if a.submitted_date]
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            use_dates = st.toggle(t("dashboard.filter_dates"), key="db_use_dates", disabled=not dated)
            start = end = None
            if use_dates and dated:
                picked = st.date_input(t("dashboard.date_range"), value=(min(dated), max(dated)),
                                       key="db_dates", format="DD/MM/YYYY")
                if isinstance(picked, (tuple, list)) and len(picked) == 2:
                    start, end = picked
        tracks = c2.multiselect(t("tracker.col_track"), list(TRACKS), key="db_tracks", placeholder=t("common.any"),
                                format_func=lambda c: label("track", c, lang()))
        sources = c3.multiselect(t("tracker.col_source"), list(SOURCES), key="db_sources", placeholder=t("common.any"),
                                 format_func=lambda c: label("source", c, lang()))

    filtered = service.filter_applications(apps, start=start, end=end, tracks=tracks, sources=sources)
    stats = service.compute_stats(filtered, today=today)
    st.caption(t("dashboard.scope", shown=len(filtered), total=len(apps)))

    kpi_row([
        (t("dashboard.kpi_total"), stats.total_submitted),
        (t("dashboard.kpi_active"), stats.active),
        (t("dashboard.kpi_interviews"), stats.interviews),
        (t("dashboard.kpi_assign"), stats.assignments_offers),
    ])

    a, b = st.columns(2)
    with a:
        section(t("dashboard.by_status"))
        charts.bar(_counts("status", stats.by_status), t("common.category"), t("common.count"), key="db_status")
    with b:
        section(t("dashboard.by_track"))
        charts.bar(_counts("track", stats.by_track), t("common.category"), t("common.count"), key="db_track")
    c, d = st.columns(2)
    with c:
        section(t("dashboard.by_source"))
        charts.bar(_counts("source", stats.by_source), t("common.category"), t("common.count"), key="db_source")
    with d:
        section(t("dashboard.weekly"))
        charts.columns_over_time(pd.DataFrame({
            t("dashboard.week"): [w.strftime("%d/%m") for w, _ in stats.weekly],
            t("common.count"): [n for _, n in stats.weekly],
        }), t("dashboard.week"), t("common.count"), key="db_weekly", x_title=t("dashboard.week_of"))

    section(t("dashboard.funnel"))
    charts.funnel(pd.DataFrame({
        t("dashboard.stage"): [label("status", s, lang()) for s, _ in stats.funnel],
        t("common.count"): [n for _, n in stats.funnel],
    }), t("dashboard.stage"), t("common.count"), key="db_funnel")
    st.caption(t("dashboard.funnel_rule"))

    section(t("dashboard.stale", days=STALE_DAYS))
    if not stats.stale:
        st.success(t("dashboard.no_stale"), icon="✅")
    else:
        st.dataframe(pd.DataFrame([{
            t("tracker.col_company"): x.company, t("tracker.col_title"): x.title,
            t("tracker.col_status"): label("status", x.status, lang()),
            t("tracker.col_last_update"): service.local_date(x.last_update_at),
            t("dashboard.days_idle"): (today - service.local_date(x.last_update_at)).days,
        } for x in stats.stale]), hide_index=True, use_container_width=True)
        st.caption(t("dashboard.stale_rule", days=STALE_DAYS))


def _counts(field: str, counts: dict[str, int]) -> pd.DataFrame:
    names = [label(field, code, lang()) if code else t("tracker.not_set") for code in counts]
    return pd.DataFrame({t("common.category"): names, t("common.count"): list(counts.values())})

