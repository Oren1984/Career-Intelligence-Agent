"""Altair chart helpers — single-series, one hue, hover tooltips and a table view.

All charts here show one measure per chart (counts), so a single blue is used
(light #2a78d6 / dark #3987e5): no categorical palette, no legends, values
available on hover and in the "data" expander.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.ui.context import t

_BLUE = {"light": "#2a78d6", "dark": "#3987e5"}
# Ordinal funnel steps (blue 250 → 600), each ≥ 2:1 against its surface.
_FUNNEL = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf"]


def _mode() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


def _show(chart: alt.Chart, df: pd.DataFrame, key: str) -> None:
    st.altair_chart(chart, use_container_width=True, theme="streamlit")
    with st.expander(t("common.view_data"), expanded=False):
        st.dataframe(df, hide_index=True, use_container_width=True, key=f"tbl_{key}")


def bar(df: pd.DataFrame, category: str, value: str, key: str, height: int | None = None) -> None:
    """Horizontal bars sorted by value (magnitude by category)."""
    if df.empty:
        st.caption(t("common.no_data"))
        return
    rows = len(df)
    chart = (
        alt.Chart(df)
        .mark_bar(color=_BLUE[_mode()], cornerRadiusEnd=4, height={"band": 0.7})
        .encode(
            x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(tickMinStep=1, grid=True)),
            y=alt.Y(f"{category}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
            tooltip=[alt.Tooltip(f"{category}:N"), alt.Tooltip(f"{value}:Q")],
        )
        .properties(height=height or max(120, 30 * rows))
    )
    text = chart.mark_text(align="left", dx=4).encode(
        text=alt.Text(f"{value}:Q"), color=alt.value("#888888")
    )
    _show(chart + text, df, key)


def columns_over_time(df: pd.DataFrame, x: str, value: str, key: str, x_title: str = "") -> None:
    """Vertical bars over an ordered time axis (e.g. submissions per week)."""
    if df.empty:
        st.caption(t("common.no_data"))
        return
    chart = (
        alt.Chart(df)
        .mark_bar(color=_BLUE[_mode()], cornerRadiusEnd=4)
        .encode(
            x=alt.X(f"{x}:O", title=x_title or None, sort=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{value}:Q", title=None, axis=alt.Axis(tickMinStep=1)),
            tooltip=[alt.Tooltip(f"{x}:O"), alt.Tooltip(f"{value}:Q")],
        )
        .properties(height=240)
    )
    _show(chart, df, key)


def funnel(df: pd.DataFrame, stage: str, value: str, key: str) -> None:
    """Ordered stages as horizontal bars, one ordinal blue step per stage."""
    if df.empty:
        st.caption(t("common.no_data"))
        return
    order = list(df[stage])
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4, height={"band": 0.75})
        .encode(
            x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(tickMinStep=1)),
            y=alt.Y(f"{stage}:N", sort=order, title=None, axis=alt.Axis(labelLimit=220)),
            color=alt.Color(f"{stage}:N", sort=order, legend=None,
                            scale=alt.Scale(domain=order, range=_FUNNEL[: len(order)])),
            tooltip=[alt.Tooltip(f"{stage}:N"), alt.Tooltip(f"{value}:Q")],
        )
        .properties(height=max(150, 34 * len(order)))
    )
    text = chart.mark_text(align="left", dx=4).encode(text=alt.Text(f"{value}:Q"), color=alt.value("#888888"))
    _show(chart + text, df, key)
