"""workspace_profile.py — Candidate profile resolution per workspace.

- Base profile files come from ``workspace_paths(ws)`` (the demo workspace has
  its own synthetic profile under demo/).
- The editable personal overlay (V1: data/personal_profile.json) is stored in
  PostgreSQL (``profile_overrides``), one row per workspace. An existing V1
  file is imported once into the personal workspace and left untouched.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import yaml

from app.candidate.profile_loader import CandidateProfile, load_candidate_profile
from app.db.models import ProfileOverride
from app.services.personal_profile_service import get_default_profile, validate_personal_profile
from app.workspace import WORKSPACE_PERSONAL, workspace_paths

logger = logging.getLogger(__name__)


def scoring_profile_for(workspace: str) -> Optional[dict[str, Any]]:
    """Profile dict for the classic keyword scorer/filter.

    Returns None for the personal workspace so the scorer keeps its V1
    behaviour (reading config/profile.yaml); other workspaces use their own file.
    """
    if workspace == WORKSPACE_PERSONAL:
        return None
    with open(workspace_paths(workspace).profile_yaml, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_override(session) -> dict[str, Any]:
    """The workspace's profile overlay (defaults when none saved). ``session`` must be workspace-bound."""
    row = session.query(ProfileOverride).first()
    merged = get_default_profile()
    if row and row.data:
        merged.update(row.data)
    return merged


def has_override(session) -> bool:
    return session.query(ProfileOverride.id).first() is not None


def save_override(session, data: dict[str, Any]) -> None:
    """Validate and upsert the workspace's overlay. Raises ValueError on invalid data."""
    errors = validate_personal_profile(data)
    if errors:
        raise ValueError("; ".join(errors))
    row = session.query(ProfileOverride).first()
    if row is None:
        session.add(ProfileOverride(data=dict(data)))
    else:
        row.data = dict(data)
    session.commit()


def import_legacy_override(session, workspace: str) -> bool:
    """Import data/personal_profile.json once into the personal workspace. Returns True if imported."""
    legacy = workspace_paths(workspace).legacy_profile_json
    if legacy is None or not legacy.exists() or has_override(session):
        return False
    try:
        with open(legacy, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        merged = get_default_profile()
        merged.update(data)
        save_override(session, merged)
        logger.info("Imported legacy personal profile from %s.", legacy)
        return True
    except Exception as exc:
        session.rollback()
        logger.warning("Could not import legacy personal profile %s: %s", legacy, exc)
        return False


def candidate_profile_for(session, workspace: str) -> CandidateProfile:
    """Full candidate profile for ``workspace`` (base files + database overlay)."""
    paths = workspace_paths(workspace)
    overlay = load_override(session) if has_override(session) else {}
    return load_candidate_profile(
        profile_dir=paths.profile_dir, config_path=paths.profile_yaml, personal_overlay=overlay,
    )
