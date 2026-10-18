# app/workspace.py
# Workspace definitions — the data boundary between the personal and demo accounts.

"""Workspaces isolate account-owned data inside the shared PostgreSQL database.

Every account-owned table carries a ``workspace`` column. PostgreSQL row-level
security only exposes rows whose workspace matches the ``app.workspace``
setting of the current transaction, which the data layer sets from the
authenticated session (see ``app/db/session.py``). Filesystem inputs
(knowledge base folder, candidate profile files) are resolved per workspace
here, so the demo account never reads the owner's files.

The set of workspaces is fixed. A workspace name is never accepted from the
browser; it is looked up from the authenticated user record.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

WORKSPACE_PERSONAL = "personal"
WORKSPACE_DEMO = "demo"
KNOWN_WORKSPACES = (WORKSPACE_PERSONAL, WORKSPACE_DEMO)
DEFAULT_WORKSPACE = WORKSPACE_PERSONAL

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class WorkspaceError(ValueError):
    """Raised for unknown or malformed workspace names."""


def validate_workspace(name: str | None) -> str:
    """Return ``name`` if it is a known workspace, else raise WorkspaceError."""
    if not isinstance(name, str) or not _NAME_RE.match(name) or name not in KNOWN_WORKSPACES:
        raise WorkspaceError(f"Unknown workspace: {name!r}")
    return name


@dataclass(frozen=True)
class WorkspacePaths:
    """Filesystem inputs owned by one workspace."""

    name: str
    kb_root: Path               # knowledge base documents (read-only input)
    profile_yaml: Path          # base candidate profile (roles, keywords, goals)
    profile_dir: Path           # skills.json / projects.json / summary.txt
    legacy_profile_json: Path | None  # V1 personal overlay file, imported once into PostgreSQL


def workspace_paths(name: str) -> WorkspacePaths:
    """Resolve the filesystem inputs for a workspace."""
    name = validate_workspace(name)
    if name == WORKSPACE_DEMO:
        demo = REPO_ROOT / "demo"
        return WorkspacePaths(
            name=name,
            kb_root=demo / "knowledge_base",
            profile_yaml=demo / "profile.yaml",
            profile_dir=demo / "candidate_profile",
            legacy_profile_json=None,
        )
    return WorkspacePaths(
        name=name,
        kb_root=Path(os.environ.get("KNOWLEDGE_BASE_DIR", REPO_ROOT / "knowledge_base")),
        profile_yaml=REPO_ROOT / "config" / "profile.yaml",
        profile_dir=REPO_ROOT / "data" / "candidate_profile",
        legacy_profile_json=REPO_ROOT / "data" / "personal_profile.json",
    )


def workspace_from_env(default: str = DEFAULT_WORKSPACE) -> str:
    """Workspace for command-line scripts: ``WORKSPACE`` env var, else ``default``."""
    return validate_workspace(os.environ.get("WORKSPACE", default))
