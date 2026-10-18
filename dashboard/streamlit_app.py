# dashboard/streamlit_app.py
# Career Decision Agent — Streamlit Dashboard (V2)

"""Career Decision Agent — Streamlit Dashboard.

Upgrades V1 with:
- Career decision scoring (multi-factor fit scores)
- Recommendation labels (Apply Now, Stretch, etc.)
- Gap analysis and action items per job
- Portfolio project matching
- Feedback signals
- Weekly strategic review
"""
import sys
import os
import subprocess
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402
from app.db.session import bind_workspace, check_db_ready, get_session_factory  # noqa: E402
from app.workspace import workspace_from_env  # noqa: E402
from app.services.job_service import JobService, VALID_STATUSES  # noqa: E402
from app.db.models import VALID_FEEDBACK_SIGNALS  # noqa: E402

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")
_PYTHON = sys.executable

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Career Decision Agent — V2",
    page_icon="🎯",
    layout="wide",
)

# ── DB bootstrap ───────────────────────────────────────────────────────────────
WORKSPACE = workspace_from_env()


@st.cache_resource
def _get_session_factory():
    check_db_ready()
    return get_session_factory()


def get_service() -> JobService:
    factory = _get_session_factory()
    session = bind_workspace(factory(), WORKSPACE)
    # Load profile for career scoring
    try:
        from app.services.workspace_profile import candidate_profile_for
        profile = candidate_profile_for(session, WORKSPACE)
        return JobService(session, profile=profile.to_dict())
    except Exception:
        return JobService(session)


# ── Source mode detection ──────────────────────────────────────────────────────
def _detect_source_mode() -> str:
    env_mode = os.environ.get("SOURCE_MODE", "").lower().strip()
    if env_mode in ("mock", "rss", "israel", "all"):
        return env_mode
    try:
        import yaml
        sources_path = os.path.join(_REPO_ROOT, "config", "sources.yaml")
        with open(sources_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        sources = data.get("sources", [])
        enabled_types = {s["source_type"] for s in sources if s.get("enabled", False)}
        israel_types = {"drushim", "alljobs", "jobnet", "jobkarov", "jobmaster", "jobify360"}
        has_israel = bool(enabled_types & israel_types)
        has_rss = "rss" in enabled_types
        has_mock = "mock" in enabled_types
        if has_israel and has_rss:
            return "all"
        elif has_israel:
            return "israel"
        elif has_rss:
            return "rss"
        elif has_mock:
            return "mock"
    except Exception:
        pass
    return "mock"


@st.cache_data(ttl=60)
def _get_source_mode() -> str:
    return _detect_source_mode()


_MODE_LABELS = {
    "mock":   "Mock (demo data)",
    "rss":    "RSS Feeds",
    "israel": "Israeli Sources",
    "all":    "All Sources",
}

_MODE_COLORS = {
    "mock": "gray", "rss": "blue", "israel": "green", "all": "orange",
}

# ── Label colors and icons ─────────────────────────────────────────────────────
_LABEL_COLORS = {
    "Apply Now":              "#1a7f37",
    "Apply After Small Fix":  "#0969da",
    "Stretch Opportunity":    "#9a6700",
    "Good Role, Wrong Timing":"#cf222e",
    "Good Company, Wrong Role":"#8250df",
    "Not Worth It":           "#6e7781",
    "Market Signal Only":     "#953800",
}

_LABEL_ICONS = {
    "Apply Now":              "🟢",
    "Apply After Small Fix":  "🔵",
    "Stretch Opportunity":    "🟡",
    "Good Role, Wrong Timing":"🔴",
    "Good Company, Wrong Role":"🟣",
    "Not Worth It":           "⚫",
    "Market Signal Only":     "🟠",
    "Not Yet Scored":         "⚪",
}


def _label_badge(label: str) -> str:
    color = _LABEL_COLORS.get(label, "#6e7781")
    icon = _LABEL_ICONS.get(label, "⚪")
    return (
        f'<span style="background-color:{color};color:white;'
        f'padding:2px 8px;border-radius:10px;font-size:0.8em;font-weight:bold;">'
        f'{icon} {label}</span>'
    )


def _run_script(script_name: str, *args: str) -> tuple[bool, str]:
    cmd = [_PYTHON, os.path.join(_SCRIPTS_DIR, script_name)] + list(args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=_REPO_ROOT,
            env={**os.environ, "WORKSPACE": WORKSPACE},
        )
        output = result.stdout + (f"\n[stderr]\n{result.stderr}" if result.stderr.strip() else "")
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Script timed out after 120 seconds."
    except Exception as exc:
        return False, f"Failed to run script: {exc}"


@st.cache_resource
def _load_candidate_profile(workspace: str):
    try:
        from app.services.workspace_profile import candidate_profile_for
        session = bind_workspace(_get_session_factory()(), workspace)
        try:
            return candidate_profile_for(session, workspace)
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Could not load candidate profile: %s", exc)
        return None


@st.cache_resource
def _get_llm_provider_name() -> str:
    try:
        from app.llm.provider_factory import get_provider
        p = get_provider()
        return p.provider_name
    except Exception:
        return "mock"


# ── Sidebar ────────────────────────────────────────────────────────────────────
source_mode = _get_source_mode()
mode_label = _MODE_LABELS.get(source_mode, source_mode)

st.sidebar.title("Career Decision Agent")
st.sidebar.caption("V2 — Personalized Job Matching")
st.sidebar.markdown("---")

st.sidebar.subheader("Source Mode")
mode_color = _MODE_COLORS.get(source_mode, "gray")
st.sidebar.markdown(
    f'<span style="background-color:{mode_color};color:white;'
    f'padding:3px 10px;border-radius:12px;font-weight:bold;font-size:0.85em;">'
    f'  {mode_label}</span>',
    unsafe_allow_html=True,
)
st.sidebar.caption("Set `SOURCE_MODE` env var to override.")
st.sidebar.markdown("---")

# ── Execution Mode ─────────────────────────────────────────────────────────────
st.sidebar.subheader("Execution Mode")
_exec_display = st.sidebar.radio(
    "exec_mode_radio",
    options=["Hybrid (RAG + Agent)", "Agent Only", "RAG Only"],
    index=0,
    label_visibility="collapsed",
    help=(
        "Hybrid: career scoring + knowledge base evidence (default).\n"
        "Agent Only: career scoring only, no KB retrieval.\n"
        "RAG Only: knowledge retrieval only, no career scoring."
    ),
)
_EXEC_KEY = {
    "Hybrid (RAG + Agent)": "hybrid",
    "Agent Only": "agent_only",
    "RAG Only": "rag_only",
}
_EXEC_LABELS = {
    "hybrid": "Hybrid (RAG + Agent)",
    "agent_only": "Agent Only",
    "rag_only": "RAG Only",
}
execution_mode = _EXEC_KEY[_exec_display]
_EXEC_COLORS = {"hybrid": "#0969da", "agent_only": "#9a6700", "rag_only": "#1a7f37"}
_EXEC_DESCS = {
    "hybrid": "Scoring + KB retrieval",
    "agent_only": "Scoring only, KB off",
    "rag_only": "KB retrieval only",
}
st.sidebar.markdown(
    f'<span style="background:{_EXEC_COLORS[execution_mode]};color:white;'
    f'padding:2px 8px;border-radius:8px;font-size:0.8em;">'
    f'{_EXEC_DESCS[execution_mode]}</span>',
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")

# ── Filters ────────────────────────────────────────────────────────────────────
st.sidebar.subheader("Filters")

from app.matching.career_scorer import ALL_LABELS  # noqa: E402
status_options = ["all"] + sorted(VALID_STATUSES)
selected_status = st.sidebar.selectbox("Status", status_options, index=0)

label_options = ["all"] + ALL_LABELS
selected_label = st.sidebar.selectbox("Recommendation Label", label_options, index=0)

match_level_options = ["all", "high", "medium", "low", "unscored"]
selected_level = st.sidebar.selectbox("Classic Match Level", match_level_options, index=0)

min_fit_score = st.sidebar.slider("Min Fit Score", 0, 100, 0, 5)
text_search = st.sidebar.text_input("Search (title / company)", "")

st.sidebar.markdown("---")

# ── Quick Actions ──────────────────────────────────────────────────────────────
st.sidebar.subheader("Quick Actions")

if st.sidebar.button("Fetch Mock Jobs", use_container_width=True):
    with st.sidebar:
        with st.spinner("Fetching mock jobs..."):
            ok, out = _run_script("fetch_jobs.py", "--mode", "mock")
    st.sidebar.success("Mock jobs fetched.") if ok else st.sidebar.error(out[:400])
    st.rerun()

if st.sidebar.button("Fetch RSS Jobs", use_container_width=True):
    with st.sidebar:
        with st.spinner("Fetching RSS feeds..."):
            ok, out = _run_script("fetch_jobs.py", "--mode", "rss")
    st.sidebar.success("RSS jobs fetched.") if ok else st.sidebar.warning(out[:400])
    st.rerun()

if st.sidebar.button("Fetch Israeli Jobs", use_container_width=True):
    with st.sidebar:
        with st.spinner("Fetching Israeli source jobs..."):
            ok, out = _run_script("fetch_jobs.py", "--mode", "israel")
    st.sidebar.success("Israeli jobs fetched.") if ok else st.sidebar.error(out[:400])
    st.rerun()

if st.sidebar.button("Score Jobs (Classic)", use_container_width=True):
    with st.sidebar:
        with st.spinner("Scoring jobs..."):
            ok, out = _run_script("score_jobs.py")
    st.sidebar.success("Scoring complete.") if ok else st.sidebar.error(out[:400])
    st.rerun()

if st.sidebar.button("Career Score Jobs (V2)", use_container_width=True,
                     help="Run multi-factor career decision scoring on all unscored jobs"):
    with st.spinner("Running career decision scoring..."):
        try:
            svc = get_service()
            n = svc.career_score_all_unscored()
            st.sidebar.success(f"Career-scored {n} jobs.")
        except Exception as exc:
            st.sidebar.error(f"Career scoring failed: {exc}")
    st.rerun()

if st.sidebar.button("Reset Demo State", use_container_width=True):
    with st.sidebar:
        with st.spinner("Resetting demo state..."):
            ok, out = _run_script("reset_demo_state.py", "--mode", "israel")
    if ok:
        st.sidebar.success("Demo state reset.")
        _get_session_factory.clear()
    else:
        st.sidebar.error(out[:400])
    st.rerun()

st.sidebar.markdown("---")
provider_name = _get_llm_provider_name()
provider_icon = "🟢" if provider_name != "mock" else "⚪"
st.sidebar.caption(f"LLM: {provider_icon} {provider_name}")
st.sidebar.caption("Scoring: career decision (V2) + keyword + semantic")

# ── Main area ──────────────────────────────────────────────────────────────────
st.title("Career Decision Agent")

try:
    service = get_service()
    summary = service.get_summary_stats()
    career_summary = service.get_career_summary_stats()
except Exception as exc:
    st.error(f"Could not load dashboard data: {exc}")
    st.stop()

# ── Summary metrics ────────────────────────────────────────────────────────────
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Total Jobs", summary["total_jobs"])
m2.metric("Career Scored", career_summary.get("career_scored", 0))
m3.metric("Apply Now", career_summary.get("label_counts", {}).get("Apply Now", 0))
m4.metric("Apply After Fix", career_summary.get("label_counts", {}).get("Apply After Small Fix", 0))
m5.metric("Avg Fit Score", f"{career_summary.get('avg_fit_score', 0):.0f}/100")
m6.metric("Unreviewed", summary["status_counts"].get("new", 0))

st.markdown("---")

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_decision, tab_jobs, tab_analytics, tab_review, tab_profile, tab_paste, tab_kb, tab_qa = st.tabs([
    "Decision Console",
    "Classic Jobs",
    "Analytics",
    "Weekly Review",
    "Candidate Profile",
    "Analyze External Job",
    "Knowledge Base",
    "Career Q&A",
])

# ─────────────────────────────────────────────────────────────────────────────
# Tab: Decision Console
# ─────────────────────────────────────────────────────────────────────────────
with tab_decision:
    st.subheader("Career Decision Console")
    st.caption(
        "Jobs scored with the multi-factor Career Decision Engine. "
        "Click 'Career Score Jobs (V2)' in the sidebar if scores are missing."
    )

    try:
        career_jobs = service.get_jobs_with_career_scores(
            status_filter=selected_status if selected_status != "all" else None,
            label_filter=selected_label if selected_label != "all" else None,
            min_fit_score=min_fit_score if min_fit_score > 0 else None,
            text_search=text_search or None,
        )
    except Exception as exc:
        st.error(f"Could not load career jobs: {exc}")
        career_jobs = []

    if not career_jobs:
        st.info(
            "No career-scored jobs yet. Run **Career Score Jobs (V2)** from the sidebar, "
            "or use **Fetch Mock Jobs** then **Career Score Jobs (V2)**."
        )
    else:
        st.write(f"**{len(career_jobs)} jobs** | sorted by fit score")

        for job in career_jobs:
            jid = job["id"]
            fit = job.get("overall_fit_score")
            label = job.get("recommendation_label", "Not Yet Scored")
            icon = _LABEL_ICONS.get(label, "⚪")
            color = _LABEL_COLORS.get(label, "#6e7781")

            # Compact header row
            with st.container():
                h1, h2, h3, h4 = st.columns([4, 2, 1, 1])
                with h1:
                    st.markdown(f"**{job['title']}** — {job['company']}")
                    st.caption(f"{job.get('location', '')} · {job.get('source', '')}")
                with h2:
                    st.markdown(_label_badge(label), unsafe_allow_html=True)
                with h3:
                    if fit is not None:
                        st.metric("Fit", f"{fit:.0f}/100", label_visibility="collapsed")
                with h4:
                    if st.button("Detail", key=f"cd_{jid}"):
                        st.session_state["career_selected_id"] = jid
                        st.rerun()

        # ── Career detail panel ─────────────────────────────────────────────
        sel_id = st.session_state.get("career_selected_id")
        if sel_id:
            detail = next((j for j in career_jobs if j["id"] == sel_id), None)

            if detail is None:
                try:
                    all_cj = service.get_jobs_with_career_scores()
                    detail = next((j for j in all_cj if j["id"] == sel_id), None)
                except Exception:
                    detail = None

            if detail:
                st.markdown("---")
                label = detail.get("recommendation_label", "Not Yet Scored")
                fit = detail.get("overall_fit_score", 0)

                # Header
                st.markdown(
                    f"## {_LABEL_ICONS.get(label, '')} {detail['title']}"
                )
                st.markdown(_label_badge(label), unsafe_allow_html=True)
                st.caption(
                    f"{detail['company']} · {detail.get('location', '')} · "
                    f"Fit: **{fit:.0f}/100**"
                )

                if detail.get("recommendation_reason"):
                    st.info(detail["recommendation_reason"])

                col_a, col_b = st.columns([3, 2])

                with col_a:
                    # Fit score breakdown
                    breakdown = detail.get("score_breakdown", {})
                    if breakdown:
                        st.markdown("#### Fit Score Breakdown")
                        import pandas as pd
                        dims = list(breakdown.keys())
                        scores = [round(v, 1) for v in breakdown.values()]
                        df_bd = pd.DataFrame({
                            "Dimension": [d.replace("_", " ").title() for d in dims],
                            "Score (0-10)": scores,
                        })
                        st.dataframe(df_bd, hide_index=True, use_container_width=True)

                    # Strengths
                    strengths = detail.get("strengths", [])
                    if strengths:
                        st.markdown("#### Strengths")
                        for s in strengths:
                            st.success(f"✓ {s}")

                    # Gaps
                    gaps = detail.get("gaps", [])
                    if gaps:
                        st.markdown("#### Gaps")
                        for g in gaps:
                            st.warning(f"△ {g}")

                    # Risks
                    risks = detail.get("risks", [])
                    if risks:
                        st.markdown("#### Risks")
                        for r in risks:
                            st.error(f"⚠ {r}")

                    # Job description
                    st.markdown("#### Job Description")
                    st.text_area(
                        "desc",
                        value=detail.get("description", ""),
                        height=180,
                        disabled=True,
                        label_visibility="collapsed",
                    )

                with col_b:
                    # Detected metadata
                    st.markdown("#### Job Intelligence")
                    meta_cols = st.columns(3)
                    meta_cols[0].metric("Seniority", detail.get("detected_seniority", "?"))
                    meta_cols[1].metric("Work Mode", detail.get("detected_work_mode", "?"))
                    meta_cols[2].metric("Direction", detail.get("career_direction_alignment", "?"))

                    if detail.get("detected_domain"):
                        st.caption(f"Domain: **{detail['detected_domain']}**")

                    # Portfolio match
                    best_proj = detail.get("best_matching_project", "")
                    if best_proj:
                        st.markdown("#### Portfolio Match")
                        st.success(f"Lead with: **{best_proj}**")
                        for h in (detail.get("portfolio_highlights") or []):
                            st.caption(f"• {h}")

                    # Gap severity
                    severity = detail.get("gap_severity", "")
                    if severity:
                        severity_colors = {"low": "🟢", "medium": "🟡", "high": "🔴"}
                        st.markdown(
                            f"#### Gap Severity: {severity_colors.get(severity, '')} {severity.upper()}"
                        )
                    easy = detail.get("easy_to_close_gaps", [])
                    hard = detail.get("hard_to_close_gaps", [])
                    if easy:
                        st.caption(f"Easy to close: {', '.join(easy[:4])}")
                    if hard:
                        st.caption(f"Hard gaps: {', '.join(hard[:3])}")

                    # Action items
                    action_items = detail.get("action_items", [])
                    if action_items:
                        st.markdown("#### Action Items")
                        for i, item in enumerate(action_items, 1):
                            st.markdown(f"**{i}.** {item}")

                    # URL
                    if detail.get("url"):
                        st.markdown(f"[View Job Posting]({detail['url']})")

                    st.markdown("---")

                    # Feedback
                    st.markdown("#### Your Feedback")
                    fb_cols = st.columns(3)
                    feedback_signals = ["liked", "applied", "not_interested",
                                        "too_senior", "wrong_direction", "irrelevant"]
                    for i, sig in enumerate(feedback_signals):
                        col = fb_cols[i % 3]
                        if col.button(sig.replace("_", " ").title(), key=f"fb_{sel_id}_{sig}"):
                            try:
                                svc_fb = get_service()
                                svc_fb.record_feedback(sel_id, sig)
                                st.success(f"Feedback '{sig}' recorded.")
                            except Exception as exc:
                                st.error(f"Feedback failed: {exc}")

                    # Status
                    st.markdown("#### Update Status")
                    new_status = st.selectbox(
                        "Status",
                        sorted(VALID_STATUSES),
                        index=sorted(VALID_STATUSES).index(detail["status"])
                        if detail["status"] in VALID_STATUSES else 0,
                        key=f"cs_status_{sel_id}",
                    )
                    if st.button("Save Status", key=f"cs_save_{sel_id}"):
                        try:
                            get_service().update_status(sel_id, new_status)
                            st.success(f"Status → {new_status}")
                        except Exception as exc:
                            st.error(str(exc))
                        st.rerun()

                    if st.button("Close", key=f"cs_close_{sel_id}"):
                        del st.session_state["career_selected_id"]
                        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Classic Jobs (V1 view preserved)
# ─────────────────────────────────────────────────────────────────────────────
with tab_jobs:
    try:
        svc2 = get_service()
        analytics = svc2.get_source_analytics()
        by_source = analytics.get("by_source", {}) if analytics else {}
    except Exception:
        by_source = {}

    if by_source:
        source_names = ", ".join(
            f"**{src}** ({cnt})" for src, cnt in sorted(by_source.items(), key=lambda x: -x[1])
        )
        st.info(f"Current data sources: {source_names}.")
    else:
        st.info("No jobs yet. Use Quick Actions in the sidebar to fetch jobs.")

    try:
        jobs = service.get_jobs_with_scores(
            status_filter=selected_status if selected_status != "all" else None,
            match_level_filter=selected_level if selected_level != "all" else None,
            text_search=text_search or None,
        )
    except Exception as exc:
        st.error(f"Could not load job list: {exc}")
        jobs = []

    st.subheader(f"Jobs ({len(jobs)} shown)")

    if not jobs:
        st.info("No jobs match the current filters.")
    else:
        _LEVEL_COLOR = {"high": "🟢", "medium": "🟡", "low": "🔴", "unscored": "⚪"}
        hcols = st.columns([3, 2, 2, 1, 1, 1, 2])
        for col, label in zip(hcols, ["Title", "Company", "Location", "Score", "Sem", "Level", "Status"]):
            col.markdown(f"**{label}**")
        st.markdown("---")

        for job in jobs:
            jid = job["id"]
            badge = _LEVEL_COLOR.get(job["match_level"], "⚪")
            row = st.columns([3, 2, 2, 1, 1, 1, 2])
            row[0].write(job["title"])
            row[1].write(job["company"])
            row[2].write(job["location"])
            row[3].write(f"{job['match_score']:.1f}")
            sem = job.get("semantic_score")
            row[4].write(f"{sem:.1f}" if sem is not None else "—")
            row[5].write(badge)
            row[6].write(job["status"])

            if st.button(f"View #{jid}", key=f"view_{jid}"):
                st.session_state["selected_job_id"] = jid
                st.rerun()

        # Detail panel (V1 preserved)
        selected_id = st.session_state.get("selected_job_id")
        if selected_id:
            detail = next((j for j in jobs if j["id"] == selected_id), None)
            if detail is None:
                try:
                    all_jobs = service.get_jobs_with_scores()
                    detail = next((j for j in all_jobs if j["id"] == selected_id), None)
                except Exception:
                    detail = None

            if detail:
                st.markdown("---")
                st.subheader(f"Job Detail — {detail['title']}")
                d1, d2 = st.columns([2, 1])

                with d1:
                    st.markdown(f"**Company:** {detail['company']}")
                    st.markdown(f"**Location:** {detail['location']}")
                    st.markdown(f"**Source:** {detail['source']}")
                    if detail["url"]:
                        st.markdown(f"**URL:** [{detail['url']}]({detail['url']})")
                    st.text_area(
                        "description",
                        value=detail["description"],
                        height=200,
                        disabled=True,
                        label_visibility="collapsed",
                    )

                with d2:
                    badge = _LEVEL_COLOR.get(detail["match_level"], "⚪")
                    final = detail.get("final_score") or detail["match_score"]
                    st.markdown(f"### {badge} {final:.1f} — {detail['match_level'].upper()}")

                    kw_score = detail.get("keyword_score")
                    sem_score = detail.get("semantic_score")
                    if kw_score is not None and sem_score is not None:
                        sc1, sc2 = st.columns(2)
                        sc1.metric("Keyword", f"{kw_score:.1f}")
                        sc2.metric("Semantic", f"{sem_score:.1f}/10")

                    if detail.get("matched_themes"):
                        st.success(", ".join(detail["matched_themes"]))
                    if detail["matched_keywords"]:
                        st.markdown("**Matched:**")
                        st.success(", ".join(detail["matched_keywords"]))
                    if detail["missing_keywords"]:
                        st.info(", ".join(detail["missing_keywords"]))
                    if detail["rejection_flags"]:
                        st.warning(", ".join(detail["rejection_flags"]))
                    st.write(detail["explanation"])

                    st.markdown("---")
                    new_status = st.selectbox(
                        "Status",
                        sorted(VALID_STATUSES),
                        index=sorted(VALID_STATUSES).index(detail["status"])
                        if detail["status"] in VALID_STATUSES else 0,
                        key=f"status_select_{selected_id}",
                    )
                    if st.button("Save", key=f"save_{selected_id}"):
                        try:
                            ok = service.update_status(selected_id, new_status)
                            if ok:
                                st.success(f"Status → {new_status}")
                        except Exception as exc:
                            st.error(str(exc))
                        st.rerun()

                    if st.button("Close", key=f"close_{selected_id}"):
                        del st.session_state["selected_job_id"]
                        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Analytics
# ─────────────────────────────────────────────────────────────────────────────
with tab_analytics:
    st.subheader("Analytics")

    try:
        analytics = service.get_source_analytics()
        career_stats = service.get_career_summary_stats()
    except Exception as exc:
        st.error(f"Could not load analytics: {exc}")
        analytics = None
        career_stats = {}

    if analytics:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Jobs", analytics["total_jobs"])
        col2.metric("Classic Scored", analytics["total_scored"])
        col3.metric("Career Scored", career_stats.get("career_scored", 0))

        st.markdown("---")

        # Recommendation label distribution
        label_counts = career_stats.get("label_counts", {})
        if any(v > 0 for v in label_counts.values()):
            st.markdown("**Recommendation Label Distribution**")
            import pandas as pd
            label_df = pd.DataFrame([
                {"Label": k, "Count": v}
                for k, v in label_counts.items() if v > 0
            ])
            if not label_df.empty:
                st.bar_chart(label_df.set_index("Label"))

        st.markdown("---")
        col_src, col_lvl = st.columns(2)

        with col_src:
            st.markdown("**Jobs by Source**")
            for src, count in sorted(analytics["by_source"].items(), key=lambda x: -x[1]):
                st.write(f"• **{src}**: {count}")

        with col_lvl:
            st.markdown("**Classic Match Levels**")
            icons = {"high": "🟢", "medium": "🟡", "low": "🔴", "unscored": "⚪"}
            for lvl, count in analytics["by_level"].items():
                st.write(f"{icons.get(lvl, '')} **{lvl.capitalize()}**: {count}")

        # Feedback summary
        try:
            fb_summary = service.get_feedback_summary()
            if fb_summary:
                st.markdown("---")
                st.markdown("**Feedback Signals**")
                for sig, count in sorted(fb_summary.items(), key=lambda x: -x[1]):
                    st.write(f"• {sig}: {count}")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Weekly Review
# ─────────────────────────────────────────────────────────────────────────────
with tab_review:
    st.subheader("Strategic Weekly Review")
    st.caption(
        "A strategic summary of your job search cycle. "
        "Requires Career Decision Scoring to be run first."
    )

    if st.button("Generate Weekly Review"):
        with st.spinner("Generating review..."):
            try:
                svc_review = get_service()
                review = svc_review.generate_weekly_review()

                if not review or not review.get("top_opportunities") and not review.get("focus_next_7_days"):
                    st.warning(
                        "Not enough career-scored data to generate a review. "
                        "Run Career Score Jobs (V2) first."
                    )
                else:
                    st.session_state["weekly_review"] = review
            except Exception as exc:
                st.error(f"Review generation failed: {exc}")

    review_data = st.session_state.get("weekly_review")

    if review_data:
        # Executive summary
        if review_data.get("executive_summary"):
            st.info(review_data["executive_summary"])

        r1, r2 = st.columns(2)

        with r1:
            # Top opportunities
            if review_data.get("top_opportunities"):
                st.markdown("#### Top Opportunities This Cycle")
                for opp in review_data["top_opportunities"]:
                    icon = _LABEL_ICONS.get(opp.get("label", ""), "⚪")
                    st.markdown(
                        f"{icon} **{opp['title']}** at {opp['company']} — "
                        f"fit: {opp.get('fit_score', 0):.0f}/100"
                    )

            # Focus next 7 days
            if review_data.get("focus_next_7_days"):
                st.markdown("#### Focus: Next 7 Days")
                for item in review_data["focus_next_7_days"]:
                    st.success(f"→ {item}")

        with r2:
            # Recurring skill gaps
            if review_data.get("recurring_missing_skills"):
                st.markdown("#### Recurring Missing Skills")
                for skill, freq in review_data["recurring_missing_skills"][:6]:
                    st.write(f"• **{skill}** (appears in {freq} job(s))")

            # Focus next 30 days
            if review_data.get("focus_next_30_days"):
                st.markdown("#### Focus: Next 30 Days")
                for item in review_data["focus_next_30_days"]:
                    st.info(f"→ {item}")

        # Direction distribution
        dist = review_data.get("direction_distribution", {})
        if dist:
            st.markdown("---")
            st.markdown("**Job Direction Distribution**")
            import pandas as pd
            dist_df = pd.DataFrame(
                [{"Track": k, "Count": v} for k, v in dist.items() if v > 0]
            )
            if not dist_df.empty:
                st.bar_chart(dist_df.set_index("Track"))

        # Strongest direction
        if review_data.get("strongest_job_direction"):
            st.success(
                f"Strongest direction for your profile: **{review_data['strongest_job_direction']}**"
            )

        # Low value patterns
        if review_data.get("low_value_patterns"):
            st.markdown("**Low-Value Patterns to Ignore**")
            for p in review_data["low_value_patterns"]:
                st.warning(f"⚠ {p}")
    else:
        st.info("Click 'Generate Weekly Review' to produce a strategic summary.")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Candidate Profile
# ─────────────────────────────────────────────────────────────────────────────
with tab_profile:
    st.subheader("Candidate Profile (V2)")

    candidate = _load_candidate_profile(WORKSPACE)

    if candidate is None:
        st.warning("Could not load candidate profile. Check data/candidate_profile/ and config/profile.yaml.")
    else:
        p1, p2 = st.columns([2, 1])

        with p1:
            if candidate.summary:
                st.markdown("**Summary**")
                st.write(candidate.summary)

            if candidate.target_roles:
                st.markdown("**Target Roles**")
                st.write(", ".join(candidate.target_roles))

            if candidate.preferred_role_track:
                st.markdown("**Primary Career Track**")
                st.write(candidate.preferred_role_track)

            col_exp, col_mode = st.columns(2)
            col_exp.metric("Experience Level", candidate.experience_level)
            col_mode.metric("Work Mode Pref", candidate.work_mode_preference)

            if candidate.short_term_goal:
                st.markdown("**Short-Term Goal**")
                st.info(candidate.short_term_goal)

            if candidate.long_term_goal:
                st.markdown("**Long-Term Goal**")
                st.info(candidate.long_term_goal)

            if candidate.preferred_domains:
                st.markdown("**Preferred Domains**")
                st.write(", ".join(candidate.preferred_domains))

            if candidate.skills:
                st.markdown("**Skills**")
                for category, skills in candidate.skills.items():
                    st.write(f"*{category.replace('_', ' ').title()}:* {', '.join(skills)}")

        with p2:
            if candidate.projects:
                st.markdown("**Portfolio Projects**")
                for proj in candidate.projects:
                    with st.expander(proj.get("name", "Project")):
                        st.write(proj.get("description", ""))
                        techs = proj.get("technologies", [])
                        if techs:
                            st.caption(f"Tech: {', '.join(techs)}")

            if candidate.preferred_technologies:
                st.markdown("**Preferred Technologies**")
                st.success(", ".join(candidate.preferred_technologies))

            if candidate.willingness_to_learn:
                st.markdown("**Willing to Learn**")
                st.info(", ".join(candidate.willingness_to_learn))

            if candidate.avoided_technologies:
                st.markdown("**Avoided Technologies**")
                st.warning(", ".join(candidate.avoided_technologies))

            if candidate.career_tracks:
                st.markdown("**Career Tracks Config**")
                primary = candidate.career_tracks.get("primary", "")
                acceptable = candidate.career_tracks.get("acceptable", [])
                avoided = candidate.career_tracks.get("avoid", [])
                if primary:
                    st.write(f"Primary: **{primary}**")
                if acceptable:
                    st.write(f"Acceptable: {', '.join(acceptable)}")
                if avoided:
                    st.write(f"Avoid: {', '.join(avoided)}")

        st.markdown("---")
        with st.expander("View Profile Prompt String (used in LLM analysis)"):
            st.code(candidate.to_prompt_string(), language=None)

    # ── Personal Profile Editor ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Edit Personal Profile")
    st.caption(
        "Stored locally at `data/personal_profile.json` (gitignored — never committed). "
        "Overrides `config/profile.yaml` values."
    )

    try:
        from app.services.workspace_profile import load_override, save_override
        _pp_session = bind_workspace(_get_session_factory()(), WORKSPACE)
        _pp = load_override(_pp_session)
    except Exception as _pp_exc:
        st.error(f"Could not load personal profile service: {_pp_exc}")
        _pp = None

    if _pp is not None:
        with st.form("personal_profile_edit_form"):
            ef1, ef2 = st.columns(2)
            pp_name = ef1.text_input("Full Name", value=_pp.get("name", ""))
            pp_headline = ef2.text_input("Headline", value=_pp.get("headline", ""),
                                         placeholder="e.g. AI Engineer | MLOps | Python")

            ef3, ef4 = st.columns(2)
            _exp_opts = ["", "junior", "mid", "senior"]
            _cur_exp = _pp.get("experience_level", "")
            pp_experience = ef3.selectbox(
                "Experience Level",
                options=_exp_opts,
                index=_exp_opts.index(_cur_exp) if _cur_exp in _exp_opts else 0,
            )
            _mode_opts = ["", "remote", "hybrid", "onsite", "any"]
            _cur_mode = _pp.get("work_mode_preference", "")
            pp_work_mode = ef4.selectbox(
                "Work Mode Preference",
                options=_mode_opts,
                index=_mode_opts.index(_cur_mode) if _cur_mode in _mode_opts else 0,
            )

            pp_target_roles = st.text_input(
                "Target Roles (comma-separated)",
                value=", ".join(_pp.get("target_roles", [])),
                placeholder="e.g. AI Engineer, MLOps Engineer",
            )
            pp_strong_skills = st.text_input(
                "Strong Skills (comma-separated)",
                value=", ".join(_pp.get("strong_skills", [])),
                placeholder="e.g. Python, RAG, Docker",
            )
            pp_weak_skills = st.text_input(
                "Weak/Known Gaps (comma-separated)",
                value=", ".join(_pp.get("weak_skills", [])),
                placeholder="e.g. Kubernetes, Scala",
            )
            pp_willingness = st.text_input(
                "Willing to Learn (comma-separated)",
                value=", ".join(_pp.get("willingness_to_learn", [])),
                placeholder="e.g. Rust, Go",
            )
            pp_preferred_tech = st.text_input(
                "Preferred Technologies (comma-separated)",
                value=", ".join(_pp.get("preferred_technologies", [])),
            )
            pp_avoided_tech = st.text_input(
                "Technologies to Avoid (comma-separated)",
                value=", ".join(_pp.get("avoided_technologies", [])),
            )

            ef5, ef6 = st.columns(2)
            pp_short_goal = ef5.text_input("Short-Term Goal", value=_pp.get("short_term_goal", ""))
            pp_long_goal = ef6.text_input("Long-Term Goal", value=_pp.get("long_term_goal", ""))

            pp_resume_summary = st.text_area(
                "Resume Summary", value=_pp.get("resume_summary", ""), height=80,
            )
            pp_notes = st.text_area("Notes", value=_pp.get("notes", ""), height=60)

            pp_save = st.form_submit_button("Save Personal Profile", type="primary")

        if pp_save:
            def _csv_to_list(s: str) -> list[str]:
                return [x.strip() for x in s.split(",") if x.strip()]

            updated = load_override(_pp_session)
            updated.update({
                "name": pp_name.strip(),
                "headline": pp_headline.strip(),
                "experience_level": pp_experience,
                "work_mode_preference": pp_work_mode,
                "target_roles": _csv_to_list(pp_target_roles),
                "strong_skills": _csv_to_list(pp_strong_skills),
                "weak_skills": _csv_to_list(pp_weak_skills),
                "willingness_to_learn": _csv_to_list(pp_willingness),
                "preferred_technologies": _csv_to_list(pp_preferred_tech),
                "avoided_technologies": _csv_to_list(pp_avoided_tech),
                "short_term_goal": pp_short_goal.strip(),
                "long_term_goal": pp_long_goal.strip(),
                "resume_summary": pp_resume_summary.strip(),
                "notes": pp_notes.strip(),
            })
            try:
                save_override(_pp_session, updated)
                st.success("Personal profile saved.")
                st.cache_resource.clear()
            except ValueError as _ve:
                st.error(f"Validation error: {_ve}")
            except Exception as _se:
                st.error(f"Could not save profile: {_se}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Analyze External Job (Paste & Analyze Mode)
# ─────────────────────────────────────────────────────────────────────────────
with tab_paste:
    st.subheader("Analyze External Job")
    st.caption(
        "Paste any job description and get a full career decision analysis instantly. "
        "No job collection required — works with any posting from any source."
    )

    # ── Execution mode display ─────────────────────────────────────────────────
    _paste_mode_descs = {
        "hybrid": "Career scoring with knowledge base evidence",
        "agent_only": "Career scoring only — knowledge base evidence disabled",
        "rag_only": "Knowledge retrieval only — career scoring disabled",
    }
    st.markdown(
        f'<span style="background:{_EXEC_COLORS[execution_mode]};color:white;'
        f'padding:3px 10px;border-radius:10px;font-size:0.85em;font-weight:bold;">'
        f'Mode: {_EXEC_LABELS[execution_mode]}</span>'
        f'&nbsp;&nbsp;<span style="color:#666;font-size:0.85em;">'
        f'{_paste_mode_descs[execution_mode]}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    # ── Input form ────────────────────────────────────────────────────────────
    with st.form("paste_job_form", clear_on_submit=False):
        col_meta1, col_meta2, col_meta3 = st.columns(3)
        input_title = col_meta1.text_input("Job Title (optional)", placeholder="e.g. AI Engineer")
        input_company = col_meta2.text_input("Company (optional)", placeholder="e.g. Acme Inc.")
        input_location = col_meta3.text_input("Location (optional)", placeholder="e.g. Tel Aviv / Remote")

        input_text = st.text_area(
            "Paste Job Description",
            height=260,
            placeholder=(
                "Paste the full job description here...\n\n"
                "The more detail you paste, the more accurate the analysis."
            ),
        )

        btn_col1, btn_col2, btn_col3 = st.columns(3)
        btn_analyze = btn_col1.form_submit_button(
            "Analyze This Job", use_container_width=True, type="primary"
        )
        btn_apply = btn_col2.form_submit_button(
            "Should I Apply?", use_container_width=True
        )
        btn_portfolio = btn_col3.form_submit_button(
            "Which Project Should I Highlight?", use_container_width=True
        )

    # ── Load analyzer (cached per profile) — uses RAGJobAnalyzer when KB ready ──
    @st.cache_resource
    def _get_manual_analyzer(workspace: str):
        try:
            from app.services.rag_job_analysis import RAGJobAnalyzer
            from app.rag.factory import knowledge_service_for
            profile = _load_candidate_profile(workspace)
            return RAGJobAnalyzer(profile=profile.to_dict(), knowledge_service=knowledge_service_for(workspace))
        except Exception as exc:
            logger.error("RAGJobAnalyzer init failed: %s", exc)
            try:
                from app.services.manual_job_analysis import ManualJobAnalyzer
                return ManualJobAnalyzer(profile=None)
            except Exception:
                return None

    # ── Helper: score-bar rendering ───────────────────────────────────────────
    def _score_bar(score: float, max_val: float = 10.0) -> str:
        pct = min(100, int(score / max_val * 100))
        color = "#1a7f37" if pct >= 70 else ("#9a6700" if pct >= 45 else "#cf222e")
        return (
            f'<div style="background:#eee;border-radius:6px;height:10px;width:100%;">'
            f'<div style="background:{color};width:{pct}%;height:10px;border-radius:6px;"></div>'
            f'</div>'
        )

    # ── Apply decision badge ──────────────────────────────────────────────────
    def _apply_badge(decision: str) -> str:
        colors = {"YES": "#1a7f37", "NO": "#cf222e", "CONDITIONAL": "#9a6700"}
        color = colors.get(decision, "#6e7781")
        return (
            f'<span style="background:{color};color:white;padding:4px 14px;'
            f'border-radius:12px;font-size:1.1em;font-weight:bold;">{decision}</span>'
        )

    # ── Handle: full analysis ─────────────────────────────────────────────────
    if btn_analyze:
        if not input_text.strip():
            st.warning("Please paste a job description before clicking Analyze.")
        else:
            _spinner_msgs = {
                "hybrid": "Running full career analysis with knowledge evidence...",
                "agent_only": "Running career decision analysis...",
                "rag_only": "Retrieving knowledge base evidence...",
            }
            with st.spinner(_spinner_msgs.get(execution_mode, "Analyzing...")):
                try:
                    analyzer = _get_manual_analyzer(WORKSPACE)
                    result = analyzer.analyze_with_mode(
                        raw_text=input_text,
                        mode=execution_mode,
                        title=input_title,
                        company=input_company,
                        location=input_location,
                    )
                    st.session_state["paste_result"] = result
                    st.session_state["paste_mode"] = "full"
                    st.session_state["paste_exec_mode"] = execution_mode
                    st.session_state["paste_exec_status"] = "success"
                except Exception as exc:
                    st.error(f"Analysis failed: {exc}")
                    st.session_state["paste_exec_status"] = "error"

    # ── Handle: Should I Apply? ───────────────────────────────────────────────
    if btn_apply:
        if not input_text.strip():
            st.warning("Please paste a job description first.")
        elif execution_mode == "rag_only":
            st.info(
                "'Should I Apply?' requires career scoring. "
                "Switch to **Agent Only** or **Hybrid** mode in the sidebar."
            )
        else:
            with st.spinner("Evaluating..."):
                try:
                    analyzer = _get_manual_analyzer(WORKSPACE)
                    if execution_mode == "agent_only":
                        apply_out = analyzer._base_analyzer.analyze_apply_only(
                            raw_text=input_text,
                            title=input_title,
                            company=input_company,
                            location=input_location,
                        )
                    else:
                        apply_out = analyzer.analyze_apply_only(
                            raw_text=input_text,
                            title=input_title,
                            company=input_company,
                            location=input_location,
                        )
                    st.session_state["paste_apply_out"] = apply_out
                    st.session_state["paste_mode"] = "apply"
                    st.session_state["paste_exec_mode"] = execution_mode
                except Exception as exc:
                    st.error(f"Evaluation failed: {exc}")

    # ── Handle: Which Project? ────────────────────────────────────────────────
    if btn_portfolio:
        if not input_text.strip():
            st.warning("Please paste a job description first.")
        elif execution_mode == "rag_only":
            st.info(
                "'Which Project?' requires career scoring. "
                "Switch to **Agent Only** or **Hybrid** mode in the sidebar."
            )
        else:
            with st.spinner("Matching portfolio..."):
                try:
                    analyzer = _get_manual_analyzer(WORKSPACE)
                    if execution_mode == "agent_only":
                        port_out = analyzer._base_analyzer.analyze_portfolio_only(
                            raw_text=input_text,
                            title=input_title,
                            company=input_company,
                            location=input_location,
                        )
                    else:
                        port_out = analyzer.analyze_portfolio_only(
                            raw_text=input_text,
                            title=input_title,
                            company=input_company,
                            location=input_location,
                        )
                    st.session_state["paste_port_out"] = port_out
                    st.session_state["paste_mode"] = "portfolio"
                    st.session_state["paste_exec_mode"] = execution_mode
                except Exception as exc:
                    st.error(f"Portfolio match failed: {exc}")

    # ── Execution status indicator ─────────────────────────────────────────────
    _exec_status_val = st.session_state.get("paste_exec_status", "")
    _last_exec_mode = st.session_state.get("paste_exec_mode", "")
    if _exec_status_val and _last_exec_mode:
        _status_color = "#1a7f37" if _exec_status_val == "success" else "#cf222e"
        _status_icon = "✓" if _exec_status_val == "success" else "✗"
        _components_ran = {
            "hybrid": "Career Scorer ✓ · KB Retrieval ✓",
            "agent_only": "Career Scorer ✓ · KB Retrieval —",
            "rag_only": "Career Scorer — · KB Retrieval ✓",
        }.get(_last_exec_mode, "")
        st.markdown(
            f'<div style="background:#f6f8fa;border-left:4px solid {_status_color};'
            f'padding:8px 14px;border-radius:4px;font-size:0.85em;margin-bottom:10px;">'
            f'<strong>Last run:</strong> {_EXEC_LABELS.get(_last_exec_mode, _last_exec_mode)}'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;'
            f'<strong>Status:</strong> {_status_icon} {_exec_status_val.capitalize()}'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;'
            f'<strong>Components:</strong> {_components_ran}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Render: Full Analysis ─────────────────────────────────────────────────
    paste_mode = st.session_state.get("paste_mode", "")

    # Import RAGOnlyResult for type-based rendering dispatch
    try:
        from app.services.rag_job_analysis import RAGOnlyResult as _RAGOnlyResult
    except ImportError:
        _RAGOnlyResult = type(None)

    if paste_mode == "full":
        result = st.session_state.get("paste_result")
        if result:
            st.markdown("---")

            # ── RAG Only mode: show retrieval results only ────────────────────
            if isinstance(result, _RAGOnlyResult):
                cov_icons = {
                    "high": "🟢 Strong", "medium": "🟡 Moderate",
                    "low": "🟠 Weak", "none": "⚪ None",
                }
                _cov_color = {
                    "high": "#1a7f37", "medium": "#9a6700",
                    "low": "#cf222e", "none": "#6e7781",
                }.get(result.coverage, "#6e7781")

                st.markdown("### Knowledge Base Evidence")
                st.markdown(
                    f'<span style="background:{_cov_color};color:white;'
                    f'padding:3px 10px;border-radius:10px;font-size:0.85em;">'
                    f'Coverage: {cov_icons.get(result.coverage, result.coverage)}</span>'
                    f'&nbsp;&nbsp;<span style="color:#666;font-size:0.85em;">'
                    f'KB size: {result.kb_size} chunks</span>',
                    unsafe_allow_html=True,
                )
                st.markdown("")

                evidence = result.retrieved_evidence
                if evidence:
                    rag_col1, rag_col2, rag_col3 = st.columns(3)
                    rag_col1.metric("Chunks Retrieved", len(evidence))
                    rag_col2.metric("Project Matches", len(result.project_evidence))
                    rag_col3.metric("Skill Matches", len(result.skill_evidence))

                    st.markdown("#### Retrieved Evidence Chunks")
                    for i, chunk in enumerate(evidence, 1):
                        score_str = f"{chunk.score:.3f}" if hasattr(chunk, "score") else ""
                        cat = getattr(chunk, "category", "")
                        fname = getattr(chunk, "file_name", "")
                        text = getattr(chunk, "text", "")
                        with st.expander(
                            f"{i}. [{cat}/{fname}] — relevance: {score_str}"
                        ):
                            st.write(text[:500] + ("…" if len(text) > 500 else ""))

                    if result.project_evidence:
                        st.markdown("#### Project Evidence")
                        for chunk in result.project_evidence:
                            fname = getattr(chunk, "file_name", "")
                            text = getattr(chunk, "text", "")
                            st.success(
                                f"**{fname}**: {text[:200]}{'…' if len(text) > 200 else ''}"
                            )

                    if result.skill_evidence:
                        st.markdown("#### Skill Evidence")
                        for chunk in result.skill_evidence:
                            fname = getattr(chunk, "file_name", "")
                            text = getattr(chunk, "text", "")
                            st.info(
                                f"**{fname}**: {text[:200]}{'…' if len(text) > 200 else ''}"
                            )

                    if result.experience_evidence:
                        st.markdown("#### Experience Evidence")
                        for chunk in result.experience_evidence:
                            fname = getattr(chunk, "file_name", "")
                            text = getattr(chunk, "text", "")
                            st.caption(
                                f"**{fname}**: {text[:200]}{'…' if len(text) > 200 else ''}"
                            )

                    if result.evidence_context:
                        with st.expander("View raw evidence context"):
                            st.text(result.evidence_context)
                else:
                    st.info(
                        "No evidence retrieved from knowledge base. "
                        "Make sure the knowledge base is ingested (Knowledge Base tab) "
                        "and contains documents relevant to this job."
                    )

                if result.missing_evidence_notes:
                    st.markdown("#### Notes")
                    for note in result.missing_evidence_notes:
                        st.warning(note)

                # End of RAG Only rendering — skip the scoring render below

            else:  # Agent Only or Hybrid: career scoring result
                # Header row
                label = result.recommendation_label
                fit = result.overall_fit_score
                pj = result.parsed_job

                st.markdown(
                    f"### {_LABEL_ICONS.get(label, '')} {pj.title} "
                    f"{'at ' + pj.company if pj.company != 'Unknown Company' else ''}"
                )
                st.markdown(_label_badge(label), unsafe_allow_html=True)

                res_c1, res_c2 = st.columns([3, 2])

                with res_c1:
                    # ── Fit Score ─────────────────────────────────────────────
                    st.markdown("#### Fit Score")
                    st.markdown(
                        f'<h2 style="margin:0;">{fit:.0f}<span style="font-size:0.5em;color:#666;">/100</span></h2>',
                        unsafe_allow_html=True,
                    )
                    rec_reason = getattr(result, "recommendation_reason", "") or getattr(getattr(result, "base_result", result), "recommendation_reason", "")
                    st.markdown(rec_reason)

                    # ── Score Breakdown ───────────────────────────────────────
                    if result.score_breakdown:
                        st.markdown("#### Dimension Breakdown")
                        for dim, val in result.score_breakdown.items():
                            label_dim = dim.replace("_", " ").title()
                            st.markdown(
                                f'<div style="margin-bottom:6px;">'
                                f'<span style="font-size:0.85em;">{label_dim}</span> '
                                f'<span style="float:right;font-size:0.85em;">{val:.1f}/10</span>'
                                f'</div>' + _score_bar(val),
                                unsafe_allow_html=True,
                            )
                            st.markdown("")   # spacer

                    # ── Should I Apply? ───────────────────────────────────────
                    st.markdown("---")
                    st.markdown("#### Should I Apply?")
                    st.markdown(
                        _apply_badge(result.apply_decision),
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"*{result.apply_explanation}*")

                    # ── Strengths ─────────────────────────────────────────────
                    if result.strengths:
                        st.markdown("#### Strengths")
                        for s in result.strengths:
                            st.success(f"✓ {s}")

                    # ── Gaps ──────────────────────────────────────────────────
                    if result.gaps:
                        st.markdown("#### Gaps")
                        for g in result.gaps:
                            st.warning(f"△ {g}")

                    # ── Risks ─────────────────────────────────────────────────
                    if result.risks:
                        st.markdown("#### Risks")
                        for r in result.risks:
                            st.error(f"⚠ {r}")

                with res_c2:
                    # ── Action Plan ───────────────────────────────────────────
                    if result.action_items:
                        st.markdown("#### Action Plan")
                        for i, item in enumerate(result.action_items, 1):
                            st.markdown(f"**{i}.** {item}")

                    # ── Portfolio ─────────────────────────────────────────────
                    st.markdown("---")
                    st.markdown("#### Portfolio Recommendation")
                    # Resolve fields from either RAGAnalysisResult or ManualAnalysisResult
                    _base = getattr(result, "base_result", result)
                    best_proj = getattr(result, "best_matching_project", "") or getattr(_base, "best_matching_project", "")
                    port_rec = getattr(_base, "portfolio_recommendation", "")
                    port_highlights = getattr(_base, "portfolio_highlights", [])
                    if best_proj:
                        st.success(f"Lead with: **{best_proj}**")
                    st.write(port_rec)
                    for h in port_highlights:
                        st.caption(f"• {h}")

                    # ── Career Direction ──────────────────────────────────────
                    st.markdown("---")
                    st.markdown("#### Career Direction")
                    detected_track = getattr(_base, "detected_track", "")
                    direction_assessment = getattr(_base, "direction_assessment", "")
                    direction_explanation = getattr(_base, "direction_explanation", "")
                    direction_advice = getattr(_base, "direction_advice", "")
                    if detected_track:
                        st.markdown(f"**Track:** {detected_track}")
                    direction_icons = {
                        "aligned":    "🟢 Aligned with your path",
                        "partial":    "🟡 Partially aligned",
                        "transition": "🔵 Good transition role",
                        "off-track":  "🔴 Off your target track",
                        "unknown":    "⚪ Direction unclear",
                    }
                    st.markdown(direction_icons.get(direction_assessment, direction_assessment))
                    if direction_explanation:
                        st.caption(direction_explanation)
                    if direction_advice:
                        st.info(direction_advice)

                    # ── Detected metadata ─────────────────────────────────────
                    st.markdown("---")
                    st.markdown("#### Detected From Posting")
                    # Support both RAGAnalysisResult and ManualAnalysisResult
                    parsed_job = getattr(result, "parsed_job", None) or getattr(getattr(result, "base_result", result), "parsed_job", None)
                    gap_severity = getattr(result, "gap_severity", "") or getattr(getattr(result, "base_result", result), "gap_severity", "")
                    easy_gaps = getattr(result, "easy_to_close_gaps", []) or getattr(getattr(result, "base_result", result), "easy_to_close_gaps", [])
                    hard_gaps = getattr(result, "hard_to_close_gaps", []) or getattr(getattr(result, "base_result", result), "hard_to_close_gaps", [])
                    gap_sev_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(gap_severity, "⚪")
                    meta_items = [
                        f"Seniority hint: **{parsed_job.detected_seniority_hint if parsed_job else 'unknown'}**",
                        f"Gap severity: {gap_sev_icon} **{gap_severity}**",
                    ]
                    if easy_gaps:
                        meta_items.append(f"Easy to close: {', '.join(easy_gaps[:3])}")
                    if hard_gaps:
                        meta_items.append(f"Hard gaps: {', '.join(hard_gaps[:3])}")
                    if parsed_job and parsed_job.extracted_technologies:
                        meta_items.append(
                            f"Tech detected: {', '.join(parsed_job.extracted_technologies[:8])}"
                        )
                    for item in meta_items:
                        st.caption(item)

                    # ── RAG Evidence (shown in Hybrid mode when KB is indexed) ─
                    evidence = getattr(result, "retrieved_evidence", [])
                    coverage = getattr(result, "coverage", "none")
                    missing_notes = getattr(result, "missing_evidence_notes", [])
                    kb_size = getattr(result, "kb_size", 0)

                    if evidence or missing_notes:
                        st.markdown("---")
                        st.markdown("#### Local Knowledge Evidence")
                        cov_icons = {"high": "🟢 Strong", "medium": "🟡 Moderate", "low": "🟠 Weak", "none": "⚪ None"}
                        st.caption(
                            f"Evidence coverage: {cov_icons.get(coverage, coverage)} "
                            f"| KB size: {kb_size} chunks"
                        )
                        if evidence:
                            with st.expander(f"View {len(evidence)} evidence chunk(s) retrieved"):
                                for i, chunk in enumerate(evidence[:5], 1):
                                    score_str = f"{chunk.score:.3f}" if hasattr(chunk, "score") else ""
                                    cat = getattr(chunk, "category", "")
                                    fname = getattr(chunk, "file_name", "")
                                    text = getattr(chunk, "text", "")
                                    st.markdown(
                                        f"**{i}. [{cat}/{fname}]** *(relevance: {score_str})*"
                                    )
                                    preview = text[:300] + ("…" if len(text) > 300 else "")
                                    st.caption(preview)
                                    st.markdown("")
                        if missing_notes:
                            st.markdown("**Missing evidence notes:**")
                            for note in missing_notes:
                                st.warning(note)
                    elif kb_size == 0 and st.session_state.get("paste_exec_mode") == "agent_only":
                        st.caption("Agent Only mode — knowledge base retrieval is disabled.")
                    elif kb_size == 0:
                        st.caption(
                            "No knowledge base indexed. "
                            "Run `python scripts/ingest_knowledge.py` to enable evidence retrieval."
                        )

    # ── Render: Should I Apply? (focused) ────────────────────────────────────
    elif paste_mode == "apply":
        apply_out = st.session_state.get("paste_apply_out")
        if apply_out:
            st.markdown("---")
            st.markdown("### Should I Apply?")
            st.markdown(
                _apply_badge(apply_out["apply_decision"]),
                unsafe_allow_html=True,
            )
            st.markdown(f"*{apply_out['apply_explanation']}*")
            st.markdown(
                f"**Fit Score:** {apply_out['overall_fit_score']:.0f}/100  "
                f"| **Label:** {_LABEL_ICONS.get(apply_out['recommendation_label'], '')} "
                f"{apply_out['recommendation_label']}"
            )
            if apply_out.get("top_actions"):
                st.markdown("**Quick Actions:**")
                for i, action in enumerate(apply_out["top_actions"], 1):
                    st.markdown(f"**{i}.** {action}")

    # ── Render: Portfolio only ────────────────────────────────────────────────
    elif paste_mode == "portfolio":
        port_out = st.session_state.get("paste_port_out")
        if port_out:
            st.markdown("---")
            st.markdown("### Which Project Should I Highlight?")

            if port_out.get("best_matching_project"):
                st.success(f"**Best match:** {port_out['best_matching_project']}")

            st.write(port_out.get("recommendation", ""))

            advice = port_out.get("emphasis_advice", [])
            if advice:
                st.markdown("**Emphasis advice:**")
                for a in advice:
                    st.markdown(f"• {a}")

            matches = port_out.get("all_matches", [])
            if matches:
                st.markdown("**All projects ranked:**")
                import pandas as pd
                df_pm = pd.DataFrame([
                    {
                        "Rank": m["highlight_order"],
                        "Project": m["project_name"],
                        "Match Score": f"{m['match_score']:.1f}/10",
                        "Matched Tech": ", ".join(m.get("matched_technologies", [])[:4]) or "—",
                    }
                    for m in matches
                ])
                st.dataframe(df_pm, hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Knowledge Base
# ─────────────────────────────────────────────────────────────────────────────
with tab_kb:
    st.subheader("Local Knowledge Base")
    st.caption(
        "Manage your local career knowledge. "
        "All files are private and processed locally — nothing leaves your machine."
    )

    @st.cache_resource
    def _get_knowledge_service(workspace: str):
        try:
            from app.rag.factory import knowledge_service_for
            return knowledge_service_for(workspace)
        except Exception as exc:
            logger.warning("KnowledgeService init failed: %s", exc)
            return None

    ks = _get_knowledge_service(WORKSPACE)

    col_kb1, col_kb2 = st.columns([2, 1])

    with col_kb1:
        if ks is None:
            st.error("Knowledge service unavailable. Check app/rag/ modules.")
        else:
            status = ks.get_status()

            if status.is_indexed:
                st.success(f"Knowledge base is indexed and ready ({status.total_chunks} chunks).")
                kb_m1, kb_m2, kb_m3 = st.columns(3)
                kb_m1.metric("Documents", status.total_documents)
                kb_m2.metric("Chunks", status.total_chunks)
                kb_m3.metric("Categories", len(status.categories))

                if status.last_ingest_iso:
                    st.caption(f"Last ingested: {status.last_ingest_iso}")

                if status.documents_by_category:
                    st.markdown("**Documents by Category:**")
                    for cat, count in sorted(status.documents_by_category.items()):
                        st.caption(f"  • {cat}: {count} document(s)")
            else:
                st.warning(
                    "Knowledge base is not yet ingested.\n\n"
                    "Add documents to `knowledge_base/` and click **Ingest Knowledge Base**."
                )

            st.markdown("---")
            st.markdown("**Knowledge Base Location:**")
            st.code(status.kb_root or "knowledge_base/")

    with col_kb2:
        st.markdown("**Actions**")

        if st.button("Ingest Knowledge Base", use_container_width=True, type="primary"):
            if ks:
                with st.spinner("Ingesting knowledge base..."):
                    try:
                        new_status = ks.ingest()
                                                if new_status.is_indexed:
                            st.success(
                                f"Ingested {new_status.total_documents} docs, "
                                f"{new_status.total_chunks} chunks."
                            )
                        else:
                            st.warning("No documents found. Add files to knowledge_base/")
                    except Exception as exc:
                        st.error(f"Ingestion failed: {exc}")
                st.rerun()

        if st.button("Rebuild Index", use_container_width=True):
            if ks:
                with st.spinner("Rebuilding index..."):
                    try:
                        new_status = ks.rebuild()
                                                st.success(
                            f"Index rebuilt: {new_status.total_documents} docs, "
                            f"{new_status.total_chunks} chunks."
                        )
                    except Exception as exc:
                        st.error(f"Rebuild failed: {exc}")
                st.rerun()

        st.markdown("---")
        st.markdown("**Quick Setup:**")
        st.code(
            "# Add your documents:\n"
            "knowledge_base/resume/\n"
            "knowledge_base/projects/\n"
            "knowledge_base/skills/\n\n"
            "# Then ingest:\n"
            "python scripts/ingest_knowledge.py",
            language=None,
        )

    st.markdown("---")
    st.markdown("**Supported file types:** `.md` `.txt` `.pdf` `.json`")
    st.markdown(
        "Personal files in `knowledge_base/` are gitignored and never committed to version control."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Career Q&A
# ─────────────────────────────────────────────────────────────────────────────
with tab_qa:
    st.subheader("Career Knowledge Q&A")
    st.caption(
        "Ask questions about your career materials. "
        "All answers are grounded in your local knowledge base."
    )

    @st.cache_resource
    def _get_qa_service(workspace: str):
        try:
            from app.rag.qa_service import CareerQAService
            return CareerQAService(knowledge_service=_get_knowledge_service(workspace))
        except Exception as exc:
            logger.warning("CareerQAService init failed: %s", exc)
            return None

    qa_service = _get_qa_service(WORKSPACE)

    # ── Check KB readiness ────────────────────────────────────────────────────
    ks_for_qa = _get_knowledge_service(WORKSPACE)
    kb_ready = ks_for_qa is not None and ks_for_qa.is_ready()

    if not kb_ready:
        st.warning(
            "The knowledge base is not ingested yet.\n\n"
            "Go to the **Knowledge Base** tab and click **Ingest Knowledge Base** first."
        )

    # ── Question input ────────────────────────────────────────────────────────
    st.markdown("#### Ask a Career Question")

    qa_examples = [
        "Which of my projects best demonstrates RAG or LLM work?",
        "What evidence do I have for Docker and Kubernetes experience?",
        "What are the recurring skill gaps I should address?",
        "Which project should I highlight for an MLOps Engineer role?",
        "What experience do I have with AWS and cloud infrastructure?",
        "Which roles align best with my current profile?",
    ]

    with st.form("career_qa_form"):
        selected_example = st.selectbox(
            "Example questions (or type your own below):",
            ["— type your own —"] + qa_examples,
        )
        qa_input = st.text_area(
            "Your question:",
            height=100,
            placeholder="e.g. Which of my projects best demonstrates backend API work?",
        )
        qa_submit = st.form_submit_button("Ask", type="primary", use_container_width=True)

    # Use example if no custom input
    if qa_submit:
        effective_question = qa_input.strip() or (
            selected_example if selected_example != "— type your own —" else ""
        )

        if not effective_question:
            st.warning("Please enter a question or select an example.")
        elif qa_service is None:
            st.error("Q&A service unavailable.")
        else:
            with st.spinner("Searching knowledge base..."):
                try:
                    answer = qa_service.ask(effective_question)
                    st.session_state["qa_answer"] = answer
                except Exception as exc:
                    st.error(f"Q&A failed: {exc}")

    # ── Display answer ────────────────────────────────────────────────────────
    qa_answer = st.session_state.get("qa_answer")

    if qa_answer is not None:
        st.markdown("---")
        st.markdown(f"**Q:** {qa_answer.question}")

        conf_icons = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🟠 Low", "none": "⚪ None"}
        st.caption(
            f"Confidence: {conf_icons.get(qa_answer.confidence, qa_answer.confidence)} "
            f"| Evidence chunks: {len(qa_answer.evidence)}"
        )

        if qa_answer.has_evidence:
            st.markdown("**Answer:**")
            st.info(qa_answer.answer)

            if qa_answer.sources:
                st.caption(f"Sources: {', '.join(qa_answer.sources)}")

            with st.expander(f"View evidence ({len(qa_answer.evidence)} chunk(s))"):
                for i, chunk in enumerate(qa_answer.evidence, 1):
                    score_str = f"{chunk.score:.3f}" if hasattr(chunk, "score") else ""
                    st.markdown(
                        f"**{i}. [{chunk.category}/{chunk.file_name}]** "
                        f"*(relevance: {score_str})*"
                    )
                    preview = chunk.text[:400] + ("…" if len(chunk.text) > 400 else "")
                    st.write(preview)
                    st.markdown("")
        else:
            st.warning(qa_answer.answer)
            st.info(
                "Tip: Add more documents to your knowledge base and re-run ingestion "
                "to get better answers."
            )

    st.markdown("---")
    st.markdown("**Example queries:**")
    for example in qa_examples[:4]:
        st.caption(f"• {example}")


# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Career Intelligence Agent — Local RAG Edition. "
    "Decision support only. No applications submitted automatically. "
    f"| Source mode: {mode_label}"
)
