"""Knowledge Base — sync status, semantic-search backend and ingestion actions."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.ui.components import empty_state, kpi_row, page_header, section
from dashboard.ui.context import knowledge_service, t, workspace
from app.workspace import WORKSPACE_DEMO


def render() -> None:
    page_header("kb.title", "kb.subtitle", help_topic="search")
    ks = knowledge_service()
    try:
        status = ks.get_status()
    except Exception as exc:
        st.error(t("common.load_failed", error=exc))
        return

    main, side = st.columns([2, 1])
    with side:
        with st.container(border=True):
            st.markdown(f"**{t('kb.actions')}**")
            if st.button(t("kb.ingest"), type="primary", use_container_width=True, help=t("kb.ingest_help")):
                _sync(ks, rebuild=False)
            if st.button(t("kb.rebuild"), use_container_width=True, help=t("kb.rebuild_help")):
                _sync(ks, rebuild=True)
            st.caption(t("kb.types"))

    with main:
        if not status.is_indexed:
            empty_state(t("kb.empty"))
        else:
            kpi_row([
                (t("kb.documents"), status.total_documents),
                (t("kb.chunks"), status.total_chunks),
                (t("kb.embedded"), status.embedded_chunks),
            ])
            if status.search_backend == "vector":
                st.success(t("kb.backend_vector"), icon="🧭")
            else:
                st.warning(t("kb.backend_tfidf"), icon="🔤")
            if status.embedding_error:
                st.caption(t("kb.model_error", error=status.embedding_error))
            if status.last_ingest_iso:
                st.caption(t("kb.last_sync", when=status.last_ingest_iso))
            if status.documents_by_category:
                section(t("kb.by_category"))
                st.dataframe(pd.DataFrame(
                    sorted(status.documents_by_category.items()), columns=[t("common.category"), t("kb.documents")]
                ), hide_index=True, use_container_width=True)

    report = st.session_state.pop("kb_last_report", None)
    if report:
        st.info(t("kb.report", **report))

    section(t("kb.location"))
    if workspace() == WORKSPACE_DEMO:
        st.caption(t("kb.demo_location"))
    else:
        st.code("knowledge_base/resume/  knowledge_base/projects/  knowledge_base/skills/ ...", language=None)
        st.caption(t("kb.personal_location"))
    st.caption(t("kb.model_note", model=status.embedding_model))


def _sync(ks, rebuild: bool) -> None:
    with st.spinner(t("kb.syncing")):
        try:
            ks.rebuild() if rebuild else ks.ingest()
        except Exception as exc:
            st.error(t("kb.sync_failed", error=exc))
            return
    r = ks.last_ingest
    if r:
        st.session_state["kb_last_report"] = dict(
            added=r.added, updated=r.updated, unchanged=r.unchanged, removed=r.removed, embedded=r.chunks_embedded,
        )
    st.rerun()
