"""factory.py — Build the workspace-scoped knowledge service used by the app and scripts."""
from __future__ import annotations

from pathlib import Path

from app.db.session import get_session_factory
from app.rag.workspace_knowledge import WorkspaceKnowledgeService


def knowledge_service_for(workspace: str, kb_root: str | Path | None = None) -> WorkspaceKnowledgeService:
    """PostgreSQL-backed knowledge service for ``workspace`` (uses DATABASE_URL)."""
    return WorkspaceKnowledgeService(get_session_factory(), workspace, kb_root=kb_root)
