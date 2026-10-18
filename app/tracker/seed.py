"""Seed synthetic tracker rows into the demo workspace (idempotent by source_ref)."""
from __future__ import annotations

import datetime as dt

import yaml

from app.db.models import Application
from app.db.session import session_scope
from app.timeutil import utcnow
from app.tracker.excel import new_row_uid
from app.tracker.service import local_today
from app.workspace import REPO_ROOT, WORKSPACE_DEMO

SEED_FILE = REPO_ROOT / "demo" / "tracker_seed.yaml"


def seed_demo_applications() -> int:
    """Insert seed rows that are not present yet; returns the number inserted."""
    with open(SEED_FILE, "r", encoding="utf-8") as fh:
        rows = yaml.safe_load(fh)["applications"]
    today, now = local_today(), utcnow()
    inserted = 0
    with session_scope(WORKSPACE_DEMO) as session:
        existing = {ref for (ref,) in session.query(Application.source_ref)
                    .filter(Application.workspace == WORKSPACE_DEMO)}
        for r in rows:
            if r["ref"] in existing:
                continue
            session.add(Application(
                row_uid=new_row_uid(), source_ref=r["ref"],
                submitted_date=today - dt.timedelta(days=r["days_ago"]),
                company=r["company"], title=r["title"], track=r["track"], source=r["source"],
                location=r.get("location", ""), salary_range=r.get("salary", ""), status=r["status"],
                notes=r.get("notes", ""), closure_reason=r.get("closure", ""), extra={},
                last_update_at=now - dt.timedelta(days=r["updated_days_ago"]),
            ))
            inserted += 1
    return inserted
