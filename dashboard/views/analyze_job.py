"""Analyze External Job — paste a posting; Hybrid / Agent Only / RAG Only execution modes."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.services.rag_job_analysis import RAGOnlyResult
from dashboard.ui.components import LABEL_ICONS, badge, label_badge, page_header, score_bar, section
from dashboard.ui.context import analyzer, t

EXEC_MODES = ["hybrid", "agent_only", "rag_only"]
EXEC_COLORS = {"hybrid": "#0969da", "agent_only": "#9a6700", "rag_only": "#1a7f37"}
_COVERAGE = {"high": "🟢", "medium": "🟡", "low": "🟠", "none": "⚪"}
_SEVERITY = {"low": "🟢", "medium": "🟡", "high": "🔴"}


def execution_mode() -> str:
    mode = st.session_state.get("exec_mode", "hybrid")
    return mode if mode in EXEC_MODES else "hybrid"


def render() -> None:
    page_header("analyze.title", "analyze.subtitle", help_topic="modes")
    mode = execution_mode()
    st.markdown(
        badge(t("analyze.mode", mode=t(f"exec.{mode}")), EXEC_COLORS[mode])
        + f'&nbsp; <span class="cia-subtitle">{t(f"exec.{mode}_desc")}</span>',
        unsafe_allow_html=True,
    )

    with st.form("paste_job_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        title = c1.text_input(t("analyze.job_title"), placeholder="AI Engineer")
        company = c2.text_input(t("analyze.company"), placeholder="Acme Inc.")
        location = c3.text_input(t("analyze.location"), placeholder="Tel Aviv / Remote")
        text = st.text_area(t("analyze.paste"), height=260, placeholder=t("analyze.paste_ph"))
        b1, b2, b3 = st.columns(3)
        do_full = b1.form_submit_button(t("analyze.btn_full"), use_container_width=True, type="primary")
        do_apply = b2.form_submit_button(t("analyze.btn_apply"), use_container_width=True)
        do_port = b3.form_submit_button(t("analyze.btn_portfolio"), use_container_width=True)

    kwargs = dict(raw_text=text, title=title, company=company, location=location)
    if (do_full or do_apply or do_port) and not text.strip():
        st.warning(t("analyze.need_text"))
    elif do_full:
        with st.spinner(t(f"analyze.spinner_{mode}")):
            try:
                st.session_state["paste_result"] = analyzer().analyze_with_mode(mode=mode, **kwargs)
                st.session_state.update(paste_mode="full", paste_exec_mode=mode, paste_exec_status="success")
            except Exception as exc:
                st.session_state["paste_exec_status"] = "error"
                st.error(t("analyze.failed", error=exc))
    elif (do_apply or do_port) and mode == "rag_only":
        st.info(t("analyze.needs_scoring"))
    elif do_apply:
        with st.spinner(t("common.working")):
            try:
                target = analyzer()._base_analyzer if mode == "agent_only" else analyzer()
                st.session_state["paste_apply_out"] = target.analyze_apply_only(**kwargs)
                st.session_state.update(paste_mode="apply", paste_exec_mode=mode)
            except Exception as exc:
                st.error(t("analyze.failed", error=exc))
    elif do_port:
        with st.spinner(t("common.working")):
            try:
                target = analyzer()._base_analyzer if mode == "agent_only" else analyzer()
                st.session_state["paste_port_out"] = target.analyze_portfolio_only(**kwargs)
                st.session_state.update(paste_mode="portfolio", paste_exec_mode=mode)
            except Exception as exc:
                st.error(t("analyze.failed", error=exc))

    _last_run()
    view = st.session_state.get("paste_mode", "")
    if view == "full" and st.session_state.get("paste_result"):
        result = st.session_state["paste_result"]
        if isinstance(result, RAGOnlyResult):
            _render_rag_only(result)
        else:
            _render_scored(result)
    elif view == "apply" and st.session_state.get("paste_apply_out"):
        _render_apply(st.session_state["paste_apply_out"])
    elif view == "portfolio" and st.session_state.get("paste_port_out"):
        _render_portfolio(st.session_state["paste_port_out"])


def _last_run() -> None:
    status = st.session_state.get("paste_exec_status", "")
    last = st.session_state.get("paste_exec_mode", "")
    if not (status and last):
        return
    components = {
        "hybrid": "analyze.components_hybrid", "agent_only": "analyze.components_agent", "rag_only": "analyze.components_rag",
    }[last]
    icon = "✓" if status == "success" else "✗"
    st.caption(f"{t('analyze.last_run')}: {t(f'exec.{last}')} · {icon} {t(f'analyze.status_{status}')} · {t(components)}")


def _evidence_list(chunks, limit: int, chars: int) -> None:
    for i, chunk in enumerate(chunks[:limit], 1):
        with st.expander(f"{i}. [{chunk.category}/{chunk.file_name}] — {t('analyze.relevance')}: {chunk.score:.3f}"):
            st.write(chunk.text[:chars] + ("…" if len(chunk.text) > chars else ""))


def _render_rag_only(result) -> None:
    section(t("analyze.kb_evidence"))
    st.caption(f"{t('analyze.coverage')}: {_COVERAGE.get(result.coverage, '')} {t(f'coverage.{result.coverage}')}"
               f" · {t('analyze.kb_size', n=result.kb_size)}")
    if not result.retrieved_evidence:
        st.info(t("analyze.no_evidence"))
    else:
        m = st.columns(3)
        m[0].metric(t("analyze.chunks"), len(result.retrieved_evidence))
        m[1].metric(t("analyze.project_matches"), len(result.project_evidence))
        m[2].metric(t("analyze.skill_matches"), len(result.skill_evidence))
        _evidence_list(result.retrieved_evidence, 20, 500)
        for key, chunks, fn in (("analyze.project_evidence", result.project_evidence, st.success),
                                ("analyze.skill_evidence", result.skill_evidence, st.info),
                                ("analyze.experience_evidence", result.experience_evidence, st.caption)):
            if chunks:
                st.markdown(f"#### {t(key)}")
                for c in chunks:
                    fn(f"**{c.file_name}**: {c.text[:200]}{'…' if len(c.text) > 200 else ''}")
        if result.evidence_context:
            with st.expander(t("analyze.raw_context")):
                st.text(result.evidence_context)
    for note in result.missing_evidence_notes:
        st.warning(note)


def _render_scored(result) -> None:
    base = getattr(result, "base_result", result)
    pj = getattr(result, "parsed_job", None) or getattr(base, "parsed_job", None)
    label = result.recommendation_label
    st.divider()
    company = f" — {pj.company}" if pj and pj.company != "Unknown Company" else ""
    st.markdown(f"### {LABEL_ICONS.get(label, '')} {pj.title if pj else ''}{company}")
    st.markdown(label_badge(label), unsafe_allow_html=True)

    c1, c2 = st.columns([3, 2])
    with c1:
        with st.container(border=True):
            st.metric(t("analyze.fit_score"), f"{result.overall_fit_score:.0f}/100")
            st.markdown(getattr(result, "recommendation_reason", "") or getattr(base, "recommendation_reason", ""))
        if result.score_breakdown:
            st.markdown(f"#### {t('analyze.dimensions')}")
            for dim, val in result.score_breakdown.items():
                st.markdown(f"{dim.replace('_', ' ').title()} — **{val:.1f}/10**")
                st.markdown(score_bar(val), unsafe_allow_html=True)
        st.markdown(f"#### {t('analyze.should_apply')}")
        st.markdown(badge(t(f"apply_decision.{result.apply_decision}"),
                          {"YES": "#1a7f37", "NO": "#cf222e", "CONDITIONAL": "#9a6700"}.get(result.apply_decision, "#6e7781")),
                    unsafe_allow_html=True)
        st.markdown(f"*{result.apply_explanation}*")
        for key, items, fn, prefix in (("decision.strengths", result.strengths, st.success, "✓"),
                                       ("decision.gaps", result.gaps, st.warning, "△"),
                                       ("decision.risks", result.risks, st.error, "⚠")):
            if items:
                st.markdown(f"#### {t(key)}")
                for item in items:
                    fn(f"{prefix} {item}")

    with c2:
        if result.action_items:
            st.markdown(f"#### {t('analyze.action_plan')}")
            for i, item in enumerate(result.action_items, 1):
                st.markdown(f"**{i}.** {item}")
        st.markdown(f"#### {t('analyze.portfolio')}")
        best = getattr(result, "best_matching_project", "") or getattr(base, "best_matching_project", "")
        if best:
            st.success(t("decision.lead_with", project=best))
        st.write(getattr(base, "portfolio_recommendation", ""))
        for h in getattr(base, "portfolio_highlights", []):
            st.caption(f"• {h}")

        st.markdown(f"#### {t('analyze.direction')}")
        if getattr(base, "detected_track", ""):
            st.markdown(f"**{t('analyze.track')}:** {base.detected_track}")
        assessment = getattr(base, "direction_assessment", "")
        if assessment:
            st.markdown(t(f"direction.{assessment}") if assessment in
                        ("aligned", "partial", "transition", "off-track", "unknown") else assessment)
        if getattr(base, "direction_explanation", ""):
            st.caption(base.direction_explanation)
        if getattr(base, "direction_advice", ""):
            st.info(base.direction_advice)

        st.markdown(f"#### {t('analyze.detected')}")
        severity = getattr(result, "gap_severity", "") or getattr(base, "gap_severity", "")
        easy = getattr(result, "easy_to_close_gaps", []) or getattr(base, "easy_to_close_gaps", [])
        hard = getattr(result, "hard_to_close_gaps", []) or getattr(base, "hard_to_close_gaps", [])
        st.caption(f"{t('decision.seniority')}: **{pj.detected_seniority_hint if pj else 'unknown'}**")
        st.caption(f"{t('decision.gap_severity')}: {_SEVERITY.get(severity, '⚪')} **{severity}**")
        if easy:
            st.caption(f"{t('decision.easy_gaps')}: {', '.join(easy[:3])}")
        if hard:
            st.caption(f"{t('decision.hard_gaps')}: {', '.join(hard[:3])}")
        if pj and pj.extracted_technologies:
            st.caption(f"{t('analyze.tech')}: {', '.join(pj.extracted_technologies[:8])}")

        evidence = getattr(result, "retrieved_evidence", [])
        notes = getattr(result, "missing_evidence_notes", [])
        kb_size = getattr(result, "kb_size", 0)
        if evidence or notes:
            st.markdown(f"#### {t('analyze.local_evidence')}")
            coverage = getattr(result, "coverage", "none")
            st.caption(f"{t('analyze.coverage')}: {_COVERAGE.get(coverage, '')} {t(f'coverage.{coverage}')} · "
                       f"{t('analyze.kb_size', n=kb_size)}")
            _evidence_list(evidence, 5, 300)
            for note in notes:
                st.warning(note)
        elif st.session_state.get("paste_exec_mode") == "agent_only":
            st.caption(t("analyze.agent_only_note"))
        elif kb_size == 0:
            st.caption(t("analyze.no_kb"))


def _render_apply(out: dict) -> None:
    section(t("analyze.should_apply"))
    st.markdown(badge(t(f"apply_decision.{out['apply_decision']}"),
                      {"YES": "#1a7f37", "NO": "#cf222e", "CONDITIONAL": "#9a6700"}.get(out["apply_decision"], "#6e7781")),
                unsafe_allow_html=True)
    st.markdown(f"*{out['apply_explanation']}*")
    st.markdown(f"**{t('analyze.fit_score')}:** {out['overall_fit_score']:.0f}/100", unsafe_allow_html=True)
    st.markdown(label_badge(out["recommendation_label"]), unsafe_allow_html=True)
    if out.get("top_actions"):
        st.markdown(f"**{t('analyze.quick_actions')}:**")
        for i, action in enumerate(out["top_actions"], 1):
            st.markdown(f"**{i}.** {action}")


def _render_portfolio(out: dict) -> None:
    section(t("analyze.btn_portfolio"))
    if out.get("best_matching_project"):
        st.success(t("analyze.best_match", project=out["best_matching_project"]))
    st.write(out.get("recommendation", ""))
    for a in out.get("emphasis_advice", []):
        st.markdown(f"• {a}")
    matches = out.get("all_matches", [])
    if matches:
        st.markdown(f"**{t('analyze.all_ranked')}:**")
        st.dataframe(pd.DataFrame([{
            t("analyze.rank"): m["highlight_order"],
            t("analyze.project"): m["project_name"],
            t("analyze.match_score"): f"{m['match_score']:.1f}/10",
            t("analyze.matched_tech"): ", ".join(m.get("matched_technologies", [])[:4]) or "—",
        } for m in matches]), hide_index=True, use_container_width=True)
