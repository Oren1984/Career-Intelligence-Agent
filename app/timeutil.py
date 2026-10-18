# app/timeutil.py
# Timezone-aware UTC helpers (replaces the deprecated datetime.utcnow()).

"""All timestamps are stored and compared as timezone-aware UTC datetimes."""
from __future__ import annotations

import datetime as _dt


def utcnow() -> _dt.datetime:
    """Current time as a timezone-aware UTC datetime."""
    return _dt.datetime.now(_dt.timezone.utc)


def ensure_utc(value: _dt.datetime | None) -> _dt.datetime | None:
    """Treat naive datetimes as UTC (SQLite returns naive values) and normalise to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value.astimezone(_dt.timezone.utc)


def today_utc() -> _dt.date:
    return utcnow().date()
