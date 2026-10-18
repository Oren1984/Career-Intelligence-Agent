"""Career Q&A — grounded answers from the workspace's knowledge base."""
from __future__ import annotations

import streamlit as st

from dashboard.ui.components import page_header, section
from dashboard.ui.context import knowledge_service, qa_service, t

_EXAMPLES = ["q1", "q2", "q3", "q4", "q5", "q6"]
_CONF = {"high": "🟢", "medium": "🟡", "low": "🟠", "none": "⚪"}


def render() -> None:
    page_header("qa.title", "qa.subtitle", help_topic="search")
    try:
        ready = knowledge_service().is_ready()
    except Exception:
        ready = False
    if not ready:
        st.warning(t("qa.not_ready"))

    with st.form("career_qa_form"):
        example = st.selectbox(t("qa.examples"), [""] + _EXAMPLES,
                               format_func=lambda k: t("qa.type_own") if not k else t(f"qa.{k}"))
        question = st.text_area(t("qa.question"), height=100, placeholder=t("qa.placeholder"))
        submitted = st.form_submit_button(t("qa.ask"), type="primary", use_container_width=True)

    if submitted:
        effective = question.strip() or (t(f"qa.{example}") if example else "")
        if not effective:
            st.warning(t("qa.need_question"))
        else:
            with st.spinner(t("qa.searching")):
                try:
                    st.session_state["qa_answer"] = qa_service().ask(effective)
                except Exception as exc:
                    st.error(t("common.load_failed", error=exc))

    answer = st.session_state.get("qa_answer")
    if answer is None:
        return
    section(t("qa.answer"))
    st.markdown(f"**Q:** {answer.question}")
    st.caption(f"{t('qa.confidence')}: {_CONF.get(answer.confidence, '')} {t(f'coverage.{answer.confidence}')}"
               f" · {t('qa.evidence_n', n=len(answer.evidence))}")
    if not answer.has_evidence:
        st.warning(answer.answer)
        st.info(t("qa.tip"))
        return
    st.info(answer.answer)
    if answer.sources:
        st.caption(f"{t('qa.sources')}: {', '.join(answer.sources)}")
    with st.expander(t("qa.view_evidence", n=len(answer.evidence))):
        for i, chunk in enumerate(answer.evidence, 1):
            st.markdown(f"**{i}. [{chunk.category}/{chunk.file_name}]** · {t('analyze.relevance')}: {chunk.score:.3f}")
            st.write(chunk.text[:400] + ("…" if len(chunk.text) > 400 else ""))
