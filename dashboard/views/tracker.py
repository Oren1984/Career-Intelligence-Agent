"""Application Tracker — editable table, Excel import (with preview) and export."""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd
import streamlit as st

from app.tracker import service
from app.tracker.excel import export_workbook, preview_workbook
from app.tracker.vocab import SOURCES, STATUSES, TRACKS, label, labels, to_code
from dashboard.ui.components import empty_state, page_header, section
from dashboard.ui.context import db, lang, t

_VER = "tracker_editor_version"


def render() -> None:
    page_header("tracker.title", "tracker.subtitle", help_topic="tracker")
    session = db()
    apps = service.list_applications(session)
    today = service.local_today()

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
        query = c1.text_input(t("filters.search"), key="tr_search", placeholder=t("tracker.search_ph"))
        statuses = c2.multiselect(t("tracker.col_status"), list(STATUSES), key="tr_status", placeholder=t("common.any"),
                                  format_func=lambda c: label("status", c, lang()))
        tracks = c3.multiselect(t("tracker.col_track"), list(TRACKS), key="tr_track", placeholder=t("common.any"),
                                format_func=lambda c: label("track", c, lang()))
        sources = c4.multiselect(t("tracker.col_source"), list(SOURCES), key="tr_source", placeholder=t("common.any"),
                                 format_func=lambda c: label("source", c, lang()))
    shown = [a for a in service.filter_applications(apps, tracks=tracks, sources=sources)
             if (not statuses or a.status in statuses) and _matches(a, query)]

    st.caption(t("tracker.count", shown=len(shown), total=len(apps)))
    if not apps:
        empty_state(t("tracker.empty"))
    _editor(shown, today)
    _import_export(apps)


def _matches(app, query: str) -> bool:
    q = (query or "").strip().casefold()
    if not q:
        return True
    return any(q in (getattr(app, f) or "").casefold() for f in ("company", "title", "location", "notes", "closure_reason"))


def _frame(apps, today: dt.date) -> pd.DataFrame:
    L = lang()
    rows = []
    for a in apps:
        unmapped = (a.extra or {}).get("unmapped") or {}
        rows.append({
            "id": a.id,
            "submitted_date": a.submitted_date,
            "company": a.company or "", "title": a.title or "",
            "track": label("track", a.track, L) or None, "source": label("source", a.source, L) or None,
            "location": a.location or "", "salary_range": a.salary_range or "",
            "status": label("status", a.status, L) or None,
            "days": service.days_since(a, today),
            "notes": a.notes or "", "closure_reason": a.closure_reason or "",
            "unmapped": "; ".join(f"{k}: {v}" for k, v in unmapped.items()),
            "last_update": service.local_date(a.last_update_at) if a.last_update_at else None,
        })
    columns = ["id", "submitted_date", "company", "title", "track", "source", "location", "salary_range",
               "status", "days", "notes", "closure_reason", "unmapped", "last_update"]
    return pd.DataFrame(rows, columns=columns)


def _editor(apps, today: dt.date) -> None:
    L = lang()
    original = _frame(apps, today)
    version = st.session_state.setdefault(_VER, 0)
    edited = st.data_editor(
        original, key=f"tracker_editor_{version}", num_rows="dynamic", hide_index=True,
        use_container_width=True,
        column_order=[c for c in original.columns if c != "id"],
        column_config={
            "id": None,
            "submitted_date": st.column_config.DateColumn(t("tracker.col_date"), format="DD/MM/YYYY"),
            "company": st.column_config.TextColumn(t("tracker.col_company"), required=True, max_chars=255),
            "title": st.column_config.TextColumn(t("tracker.col_title"), required=True, max_chars=255),
            "track": st.column_config.SelectboxColumn(t("tracker.col_track"), options=labels("track", L)),
            "source": st.column_config.SelectboxColumn(t("tracker.col_source"), options=labels("source", L)),
            "location": st.column_config.TextColumn(t("tracker.col_location"), max_chars=255),
            "salary_range": st.column_config.TextColumn(t("tracker.col_salary"), max_chars=120),
            "status": st.column_config.SelectboxColumn(t("tracker.col_status"), options=labels("status", L)),
            "days": st.column_config.NumberColumn(t("tracker.col_days"), disabled=True, format="%d"),
            "notes": st.column_config.TextColumn(t("tracker.col_notes"), width="large"),
            "closure_reason": st.column_config.TextColumn(t("tracker.col_closure"), width="medium"),
            "unmapped": st.column_config.TextColumn(t("tracker.col_unmapped"), disabled=True,
                                                    help=t("tracker.unmapped_help")),
            "last_update": st.column_config.DateColumn(t("tracker.col_last_update"), disabled=True,
                                                       format="DD/MM/YYYY"),
        },
    )
    if st.button(t("tracker.save"), type="primary", icon="💾"):
        _save(original, edited)


def _clean(value):
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NaT:
        return None
    return value


def _values(row) -> dict:
    d = _clean(row.get("submitted_date"))
    if isinstance(d, pd.Timestamp):
        d = d.date()
    elif isinstance(d, dt.datetime):
        d = d.date()
    return {
        "submitted_date": d,
        **{f: (_clean(row.get(f)) or "") for f in ("company", "title", "location", "salary_range", "notes",
                                                   "closure_reason")},
        **{f: to_code(f, _clean(row.get(f))) for f in ("track", "source", "status")},
    }


def _save(original: pd.DataFrame, edited: pd.DataFrame) -> None:
    session = db()
    before = {int(r["id"]): r for r in original.to_dict("records")}
    after_ids = {int(i) for i in edited["id"].dropna()}
    errors, added, updated = [], 0, 0
    try:
        for n, row in enumerate(edited.to_dict("records"), start=1):
            row_id = _clean(row.get("id"))
            values = _values(row)
            try:
                if row_id is None:
                    if any(values.get(f) for f in ("company", "title", "notes")):
                        service.create(session, values)
                        added += 1
                else:
                    old = before.get(int(row_id))
                    if old is not None and _values(old) != values:
                        updated += int(service.update(session, int(row_id), values))
            except service.ValidationError as exc:
                errors.append(t("tracker.row_error", n=n, error=t(f"tracker.err_{exc}")))
        deleted_ids = set(before) - after_ids
        if errors:
            session.rollback()
            for e in errors:
                st.error(e)
            return
        deleted = service.delete(session, deleted_ids)
        session.commit()
    except Exception as exc:
        session.rollback()
        st.error(t("common.save_failed") + f" ({exc})")
        return
    st.session_state[_VER] = st.session_state.get(_VER, 0) + 1
    st.toast(t("tracker.saved", added=added, updated=updated, deleted=deleted), icon="✅")
    st.rerun()


def _import_export(apps) -> None:
    section(t("tracker.excel"))
    left, right = st.columns(2)
    with right:
        with st.container(border=True):
            st.markdown(f"**{t('tracker.export')}**")
            st.caption(t("tracker.export_caption"))
            st.download_button(
                t("tracker.export_btn"), data=export_workbook(apps, lang()),
                file_name=f"job_search_tracker_{service.local_today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon="⬇️", use_container_width=True, disabled=not apps,
            )
    with left:
        with st.container(border=True):
            st.markdown(f"**{t('tracker.import')}**")
            st.caption(t("tracker.import_caption"))
            upload = st.file_uploader(t("tracker.upload"), type=["xlsx"], key=f"tr_upload_{st.session_state.get(_VER, 0)}")
            if upload is None:
                return
            preview = preview_workbook(upload.getvalue(), service.existing_keys(db()))
            if preview.error:
                st.error(t("tracker.import_error", error=preview.error))
                return
            st.markdown(t("tracker.preview", sheet=preview.sheet))
            st.dataframe(pd.DataFrame([
                (t("tracker.p_ready"), len(preview.rows)),
                (t("tracker.p_duplicates"), preview.count("duplicate")),
                (t("tracker.p_blank"), preview.blank_rows),
                (t("tracker.p_incomplete"), len(preview.incomplete_rows)),
                (t("tracker.p_invalid_dates"), preview.count("invalid_date")),
                (t("tracker.p_unmapped"), preview.count("unmapped")),
                (t("tracker.p_extra_columns"), len(preview.extra_columns)),
            ], columns=[t("tracker.p_item"), t("common.count")]), hide_index=True, use_container_width=True)
            if preview.issues:
                with st.expander(t("tracker.p_details", n=len(preview.issues))):
                    st.dataframe(pd.DataFrame([
                        {t("tracker.p_row"): i.row, t("tracker.p_kind"): t(f"tracker.kind_{i.kind}"),
                         t("tracker.p_field"): i.field} for i in preview.issues
                    ]), hide_index=True, use_container_width=True)
            include = st.checkbox(t("tracker.include_incomplete"), key="tr_inc",
                                  disabled=not preview.incomplete_rows)
            total = len(preview.rows) + (len(preview.incomplete_rows) if include else 0)
            if st.button(t("tracker.import_btn", n=total), type="primary", disabled=total == 0,
                         use_container_width=True):
                n = service.commit_import(db(), preview, include_incomplete=include)
                st.session_state[_VER] = st.session_state.get(_VER, 0) + 1
                st.toast(t("tracker.imported", n=n), icon="✅")
                st.rerun()
