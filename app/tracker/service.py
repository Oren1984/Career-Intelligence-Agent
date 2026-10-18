"""Tracker data access and statistics.

Every function takes a workspace-bound session: row-level security limits it
to that workspace, and queries also filter on the workspace explicitly.
"""
from __future__ import annotations

import datetime as dt
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from app.db.models import Application
from app.timeutil import ensure_utc, utcnow
from app.tracker.excel import CONTROLLED, TEXT_FIELDS, ImportPreview, dedup_key, new_row_uid
from app.tracker.vocab import (
    ACTIVE_STATUSES, ASSIGNMENT_OFFER_STATUSES, FUNNEL, INTERVIEW_STATUSES, SOURCES, STALE_DAYS,
    STATUSES, TRACKS,
)

EDITABLE = ("submitted_date",) + TEXT_FIELDS + CONTROLLED


def _tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Jerusalem"))


def local_today() -> dt.date:
    """'Today' in the user's timezone (APP_TIMEZONE, default Asia/Jerusalem) — like Excel's TODAY()."""
    return dt.datetime.now(_tz()).date()


def local_date(ts: dt.datetime) -> dt.date:
    return ensure_utc(ts).astimezone(_tz()).date()


def _workspace(session) -> str:
    return session.info["workspace"]


def list_applications(session) -> list[Application]:
    rows = session.query(Application).filter(Application.workspace == _workspace(session)).all()
    return sorted(rows, key=lambda a: (a.submitted_date is None, -(a.submitted_date.toordinal() if a.submitted_date else 0), a.id))


def existing_keys(session) -> set[tuple]:
    keys = set()
    for a in list_applications(session):
        raw = ((a.extra or {}).get("unmapped") or {}).get("submitted_date", "")
        keys.add(dedup_key(a.submitted_date, raw, a.company or "", a.title or ""))
    return keys


def days_since(app: Application, today: Optional[dt.date] = None) -> Optional[int]:
    if not app.submitted_date:
        return None
    return ((today or local_today()) - app.submitted_date).days


def _initial_update(submitted: Optional[dt.date]) -> dt.datetime:
    """Imported rows have no update history: their last known activity is the submission date."""
    if submitted:
        return dt.datetime.combine(submitted, dt.time(12, 0), tzinfo=dt.timezone.utc)
    return utcnow()


# ── Writes ───────────────────────────────────────────────────────────────────

class ValidationError(ValueError):
    pass


def validate(values: dict[str, Any]) -> None:
    if not (values.get("company") or "").strip() or not (values.get("title") or "").strip():
        raise ValidationError("company_title_required")
    for fld, vocab in (("status", STATUSES), ("track", TRACKS), ("source", SOURCES)):
        if values.get(fld) and values[fld] not in vocab:
            raise ValidationError(f"invalid_{fld}")
    d = values.get("submitted_date")
    if d is not None and not isinstance(d, dt.date):
        raise ValidationError("invalid_date")


def create(session, values: dict[str, Any]) -> Application:
    validate(values)
    app = Application(row_uid=new_row_uid(), extra={}, last_update_at=utcnow(),
                      **{k: values.get(k) if k not in TEXT_FIELDS else (values.get(k) or "").strip()
                         for k in EDITABLE})
    session.add(app)
    return app


def update(session, app_id: int, values: dict[str, Any]) -> bool:
    """Apply changed fields; returns True if anything changed (then last_update_at moves)."""
    app = session.query(Application).filter(
        Application.id == app_id, Application.workspace == _workspace(session)).first()
    if app is None:
        raise ValidationError("not_found")
    merged = {k: getattr(app, k) for k in EDITABLE} | {k: v for k, v in values.items() if k in EDITABLE}
    for k in TEXT_FIELDS:
        merged[k] = (merged.get(k) or "").strip()
    validate(merged)
    changed = [k for k in EDITABLE if merged[k] != getattr(app, k)]
    if not changed:
        return False
    extra = dict(app.extra or {})
    unmapped = dict(extra.get("unmapped") or {})
    for k in changed:
        setattr(app, k, merged[k])
        if merged[k]:
            unmapped.pop(k, None)   # an explicit valid value replaces a kept raw import value
    extra["unmapped"] = unmapped
    app.extra = {k: v for k, v in extra.items() if v}
    app.last_update_at = utcnow()
    return True


def delete(session, app_ids: Iterable[int]) -> int:
    ids = list(app_ids)
    if not ids:
        return 0
    return session.query(Application).filter(
        Application.id.in_(ids), Application.workspace == _workspace(session)
    ).delete(synchronize_session=False)


def commit_import(session, preview: ImportPreview, include_incomplete: bool = False) -> int:
    rows = list(preview.rows) + (list(preview.incomplete_rows) if include_incomplete else [])
    for r in rows:
        session.add(Application(
            row_uid=new_row_uid(), source_ref=r.get("source_ref"), submitted_date=r.get("submitted_date"),
            **{k: r.get(k) or "" for k in TEXT_FIELDS}, **{k: r.get(k) for k in CONTROLLED},
            extra=r.get("extra") or {}, last_update_at=_initial_update(r.get("submitted_date")),
        ))
    session.commit()
    return len(rows)


# ── Statistics (workbook definitions) ───────────────────────────────────────

@dataclass
class TrackerStats:
    total_submitted: int = 0          # COUNTIF(B, "<>")
    active: int = 0                   # statuses in ACTIVE_STATUSES
    interviews: int = 0               # initial call + professional interview
    assignments_offers: int = 0       # home assignment + offer
    by_status: dict[str, int] = field(default_factory=dict)   # code (or "" for unset/unmapped) → n
    by_track: dict[str, int] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)
    weekly: list[tuple[dt.date, int]] = field(default_factory=list)   # week start (Monday) → n
    funnel: list[tuple[str, int]] = field(default_factory=list)
    stale: list[Application] = field(default_factory=list)


def filter_applications(apps: list[Application], start: Optional[dt.date] = None, end: Optional[dt.date] = None,
                        tracks: Iterable[str] = (), sources: Iterable[str] = ()) -> list[Application]:
    tracks, sources = set(tracks), set(sources)
    out = []
    for a in apps:
        if (start or end) and a.submitted_date is None:
            continue
        if start and a.submitted_date < start:
            continue
        if end and a.submitted_date > end:
            continue
        if tracks and a.track not in tracks:
            continue
        if sources and a.source not in sources:
            continue
        out.append(a)
    return out


def compute_stats(apps: list[Application], today: Optional[dt.date] = None) -> TrackerStats:
    today = today or local_today()
    s = TrackerStats()
    s.total_submitted = sum(1 for a in apps if a.submitted_date is not None)
    s.active = sum(1 for a in apps if a.status in ACTIVE_STATUSES)
    s.interviews = sum(1 for a in apps if a.status in INTERVIEW_STATUSES)
    s.assignments_offers = sum(1 for a in apps if a.status in ASSIGNMENT_OFFER_STATUSES)

    for attr, target, vocab in (("status", s.by_status, STATUSES), ("track", s.by_track, TRACKS),
                                ("source", s.by_source, SOURCES)):
        counts = Counter(getattr(a, attr) or "" for a in apps)
        for code in vocab:
            if counts.get(code):
                target[code] = counts[code]
        if counts.get(""):
            target[""] = counts[""]

    weeks = Counter(a.submitted_date - dt.timedelta(days=a.submitted_date.weekday())
                    for a in apps if a.submitted_date)
    if weeks:
        week, last = min(weeks), max(weeks)
        while week <= last:
            s.weekly.append((week, weeks.get(week, 0)))
            week += dt.timedelta(days=7)

    population = [a for a in apps if a.submitted_date is not None]
    reached = [FUNNEL.index(a.status) if a.status in FUNNEL else 0 for a in population]
    s.funnel = [(stage, sum(1 for r in reached if r >= i)) for i, stage in enumerate(FUNNEL)]

    s.stale = sorted(
        (a for a in apps if a.status in ACTIVE_STATUSES and a.last_update_at is not None
         and (today - local_date(a.last_update_at)).days >= STALE_DAYS),
        key=lambda a: ensure_utc(a.last_update_at),
    )
    return s
