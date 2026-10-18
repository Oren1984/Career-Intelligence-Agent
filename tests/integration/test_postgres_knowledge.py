"""Knowledge base on PostgreSQL: idempotent sync, vector search, TF-IDF fallback, isolation."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.db.models import KnowledgeChunk
from app.db.session import get_session_factory, session_scope
from app.rag.embeddings import EmbeddingUnavailable
from app.rag.workspace_knowledge import WorkspaceKnowledgeService

from tests.integration.conftest import FakeEmbedder

pytestmark = pytest.mark.postgres

DOCS = {
    "projects/k8s_platform.md": "# Platform\n\nBuilt a Kubernetes platform with Helm charts and ArgoCD deployments.",
    "skills/observability.md": "# Observability\n\nPrometheus and Grafana dashboards with SLO alerting for services.",
    "resume/summary.md": "# Summary\n\nBaker who managed daily bread inventory and staff schedules carefully.",
}


def _write(root: Path, docs: dict[str, str]) -> Path:
    for rel, content in docs.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _service(app_url, ws, root, embedder=None, **kw):
    embedder = embedder if embedder is not None else FakeEmbedder()
    return WorkspaceKnowledgeService(
        get_session_factory(app_url), ws, kb_root=root,
        embedder_provider=lambda: embedder, vector_floor=0.0, **kw,
    )


def _chunk_ids(app_url, ws):
    with session_scope(ws, app_url) as s:
        return sorted(r.chunk_id for r in s.query(KnowledgeChunk).all())


def test_ingest_embeds_and_vector_search_ranks_relevant_chunk(app_url, tmp_path):
    ks = _service(app_url, "demo", _write(tmp_path, DOCS))
    status = ks.ingest()
    assert status.total_documents == 3
    assert status.embedded_chunks == status.total_chunks > 0
    assert status.search_backend == "vector"

    result = ks.retrieve("kubernetes helm argocd platform")
    assert result.method == "vector"
    assert result.chunks[0].file_name == "k8s_platform.md"


def test_reingest_is_idempotent_and_replaces_or_removes_chunks(app_url, tmp_path):
    root = _write(tmp_path, DOCS)
    ks = _service(app_url, "demo", root)
    ks.ingest()
    before = _chunk_ids(app_url, "demo")

    ks.ingest()
    assert ks.last_ingest.unchanged == 3 and ks.last_ingest.added == ks.last_ingest.updated == 0
    assert _chunk_ids(app_url, "demo") == before

    # Replace a document: its old text must no longer be retrievable.
    (root / "projects/k8s_platform.md").write_text("# Platform\n\nNow focused on Terraform modules for AWS networking.", encoding="utf-8")
    ks.ingest()
    assert ks.last_ingest.updated == 1
    texts = [c.text for c in ks.retrieve("terraform aws networking", top_k=10).chunks]
    assert any("Terraform" in t for t in texts)
    assert not any("ArgoCD" in t for t in ks.retrieve("argocd helm", top_k=10).chunks for t in [t.text])

    # Delete a document: its chunks are removed.
    (root / "resume/summary.md").unlink()
    ks.ingest()
    assert ks.last_ingest.removed == 1
    assert not [c for c in _chunk_ids(app_url, "demo") if c.startswith("resume/")]


def test_rebuild_reembeds_everything(app_url, tmp_path):
    embedder = FakeEmbedder()
    ks = _service(app_url, "demo", _write(tmp_path, DOCS), embedder=embedder)
    ks.ingest()
    calls = embedder.calls
    ks.rebuild()
    assert embedder.calls == calls + 3


def test_tfidf_fallback_when_embeddings_unavailable(app_url, tmp_path):
    def unavailable():
        raise EmbeddingUnavailable("model files missing (simulated)")

    root = _write(tmp_path, DOCS)
    ks = WorkspaceKnowledgeService(get_session_factory(app_url), "demo", kb_root=root, embedder_provider=unavailable)
    status = ks.ingest()
    assert status.total_chunks > 0 and status.embedded_chunks == 0
    assert status.search_backend == "tfidf"

    result = ks.retrieve("kubernetes helm")
    assert result.method == "tfidf"
    assert "simulated" in result.fallback_reason
    assert result.chunks and result.chunks[0].file_name == "k8s_platform.md"


def test_failing_embedder_during_ingest_keeps_chunks_and_falls_back(app_url, tmp_path):
    ks = _service(app_url, "demo", _write(tmp_path, DOCS), embedder=FakeEmbedder(fail=True))
    status = ks.ingest()
    assert status.total_chunks > 0 and status.embedded_chunks == 0
    assert "simulated embedding failure" in ks.last_ingest.embedding_error

    result = ks.retrieve("prometheus grafana")
    assert result.method == "tfidf"
    assert result.chunks[0].file_name == "observability.md"

    # Once embeddings work again, a normal ingest backfills the vectors.
    healed = _service(app_url, "demo", ks._kb_root)
    assert healed.ingest().embedded_chunks == status.total_chunks
    assert healed.retrieve("prometheus grafana").method == "vector"


def test_vector_query_error_falls_back_to_tfidf(app_url, tmp_path):
    class BadQuery(FakeEmbedder):
        def embed_query(self, text):
            return [0.0] * 3   # wrong dimension → database error

    ks = _service(app_url, "demo", _write(tmp_path, DOCS), embedder=BadQuery())
    ks.ingest()
    result = ks.retrieve("kubernetes")
    assert result.method == "tfidf"
    assert result.fallback_reason.startswith("Vector search failed")
    assert result.chunks


def test_search_is_isolated_between_workspaces_in_both_paths(app_url, tmp_path):
    demo_root = _write(tmp_path / "demo", {"projects/demo.md": "# Demo\n\nDemo kubernetes platform project with helm."})
    personal_root = _write(tmp_path / "personal", {"projects/secret.md": "# Secret\n\nConfidential kubernetes migration for a private client."})
    _service(app_url, "demo", demo_root).ingest()
    _service(app_url, "personal", personal_root).ingest()

    demo_vec = _service(app_url, "demo", demo_root)
    demo_tfidf = _service(app_url, "demo", demo_root, search_backend="tfidf")
    for ks in (demo_vec, demo_tfidf):
        result = ks.retrieve("confidential kubernetes migration private client", top_k=10)
        assert result.chunks, ks
        assert {c.file_name for c in result.chunks} == {"demo.md"}
        assert ks.get_status().total_documents == 1
    assert demo_vec.retrieve("kubernetes").method == "vector"
    assert demo_tfidf.retrieve("kubernetes").method == "tfidf"

    personal = _service(app_url, "personal", personal_root, search_backend="tfidf")
    assert {c.file_name for c in personal.retrieve("demo helm kubernetes", top_k=10).chunks} == {"secret.md"}


def test_missing_kb_folder_does_not_wipe_existing_chunks(app_url, tmp_path):
    root = _write(tmp_path / "kb", DOCS)
    _service(app_url, "demo", root).ingest()
    count = len(_chunk_ids(app_url, "demo"))
    _service(app_url, "demo", tmp_path / "does-not-exist").ingest()
    assert len(_chunk_ids(app_url, "demo")) == count


@pytest.mark.model
def test_real_model_multilingual_retrieval(app_url):
    """Real multilingual-e5-small over the synthetic demo KB (English + Hebrew)."""
    from app.rag.embeddings import get_embedder, reset_embedder
    from app.workspace import workspace_paths

    reset_embedder()
    try:
        get_embedder()
    except EmbeddingUnavailable as exc:
        pytest.skip(f"embedding model not available locally: {exc}")

    ks = WorkspaceKnowledgeService(get_session_factory(app_url), "demo", kb_root=workspace_paths("demo").kb_root)
    status = ks.ingest()
    assert status.search_backend == "vector" and status.embedded_chunks == status.total_chunks

    he = ks.retrieve("מה הפערים שצריך לסגור בתכנות?", top_k=3)
    assert he.method == "vector"
    assert he.chunks and he.chunks[0].file_name == "career_strategy_he.md"

    en = ks.retrieve("Which project shows MLflow model deployment with canary rollouts?", top_k=3)
    assert en.chunks and en.chunks[0].file_name == "ml_delivery_pipeline.md"
