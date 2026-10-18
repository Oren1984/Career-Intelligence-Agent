"""Candidate Profile — view the merged profile and edit the workspace's personal overlay."""
from __future__ import annotations

import streamlit as st

from app.services.workspace_profile import import_legacy_override, load_override, save_override
from dashboard.ui.components import page_header, section
from dashboard.ui.context import candidate_profile, clear_profile_caches, db, t, workspace

_EXP = ["", "junior", "mid", "senior"]
_MODES = ["", "remote", "hybrid", "onsite", "any"]


def _csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def render() -> None:
    page_header("profile.title", "profile.subtitle")
    if import_legacy_override(db(), workspace()):
        clear_profile_caches()
        st.toast(t("profile.legacy_imported"), icon="📥")

    candidate = candidate_profile()
    if candidate is None:
        st.warning(t("profile.load_failed"))
    else:
        _view(candidate)

    section(t("profile.edit"))
    st.caption(t("profile.edit_caption"))
    _editor()


def _view(c) -> None:
    p1, p2 = st.columns([2, 1])
    with p1:
        with st.container(border=True):
            if c.summary:
                st.markdown(f"**{t('profile.summary')}**")
                st.write(c.summary)
            if c.target_roles:
                st.markdown(f"**{t('profile.target_roles')}:** " + ", ".join(c.target_roles))
            if c.preferred_role_track:
                st.markdown(f"**{t('profile.primary_track')}:** {c.preferred_role_track}")
            m1, m2 = st.columns(2)
            m1.metric(t("profile.experience"), c.experience_level)
            m2.metric(t("profile.work_mode"), c.work_mode_preference)
            if c.short_term_goal:
                st.markdown(f"**{t('profile.short_goal')}**")
                st.info(c.short_term_goal)
            if c.long_term_goal:
                st.markdown(f"**{t('profile.long_goal')}**")
                st.info(c.long_term_goal)
            if c.preferred_domains:
                st.markdown(f"**{t('profile.domains')}:** " + ", ".join(c.preferred_domains))
            if c.skills:
                st.markdown(f"**{t('profile.skills')}**")
                for category, skills in c.skills.items():
                    st.write(f"*{category.replace('_', ' ').title()}:* {', '.join(skills)}")
    with p2:
        if c.projects:
            st.markdown(f"**{t('profile.projects')}**")
            for proj in c.projects:
                with st.expander(proj.get("name", "Project")):
                    st.write(proj.get("description", ""))
                    if proj.get("technologies"):
                        st.caption(", ".join(proj["technologies"]))
        if c.preferred_technologies:
            st.markdown(f"**{t('profile.preferred_tech')}**")
            st.success(", ".join(c.preferred_technologies))
        if c.willingness_to_learn:
            st.markdown(f"**{t('profile.learn')}**")
            st.info(", ".join(c.willingness_to_learn))
        if c.avoided_technologies:
            st.markdown(f"**{t('profile.avoided_tech')}**")
            st.warning(", ".join(c.avoided_technologies))
        tracks = c.career_tracks or {}
        if tracks:
            st.markdown(f"**{t('profile.tracks')}**")
            if tracks.get("primary"):
                st.write(f"{t('profile.track_primary')}: **{tracks['primary']}**")
            if tracks.get("acceptable"):
                st.write(f"{t('profile.track_ok')}: {', '.join(tracks['acceptable'])}")
            if tracks.get("avoid"):
                st.write(f"{t('profile.track_avoid')}: {', '.join(tracks['avoid'])}")
    with st.expander(t("profile.prompt_string")):
        st.code(c.to_prompt_string(), language=None)


def _editor() -> None:
    pp = load_override(db())
    with st.form("personal_profile_edit_form"):
        a, b = st.columns(2)
        name = a.text_input(t("profile.f_name"), value=pp.get("name", ""))
        headline = b.text_input(t("profile.f_headline"), value=pp.get("headline", ""))
        c, d = st.columns(2)
        exp = c.selectbox(t("profile.experience"), _EXP,
                          index=_EXP.index(pp.get("experience_level", "")) if pp.get("experience_level", "") in _EXP else 0)
        mode = d.selectbox(t("profile.work_mode"), _MODES,
                           index=_MODES.index(pp.get("work_mode_preference", "")) if pp.get("work_mode_preference", "") in _MODES else 0)
        fields = {}
        for key in ("target_roles", "strong_skills", "weak_skills", "willingness_to_learn",
                    "preferred_technologies", "avoided_technologies"):
            fields[key] = st.text_input(t(f"profile.f_{key}"), value=", ".join(pp.get(key, [])))
        e, g = st.columns(2)
        short_goal = e.text_input(t("profile.short_goal"), value=pp.get("short_term_goal", ""))
        long_goal = g.text_input(t("profile.long_goal"), value=pp.get("long_term_goal", ""))
        resume = st.text_area(t("profile.f_resume_summary"), value=pp.get("resume_summary", ""), height=80)
        notes = st.text_area(t("profile.f_notes"), value=pp.get("notes", ""), height=60)
        submitted = st.form_submit_button(t("profile.save"), type="primary")

    if submitted:
        updated = load_override(db())
        updated.update({
            "name": name.strip(), "headline": headline.strip(),
            "experience_level": exp, "work_mode_preference": mode,
            **{k: _csv(v) for k, v in fields.items()},
            "short_term_goal": short_goal.strip(), "long_term_goal": long_goal.strip(),
            "resume_summary": resume.strip(), "notes": notes.strip(),
        })
        try:
            save_override(db(), updated)
        except ValueError as exc:
            st.error(t("profile.invalid", error=exc))
            return
        except Exception as exc:
            st.error(t("common.save_failed") + f" ({exc})")
            return
        clear_profile_caches()
        st.toast(t("profile.saved"), icon="✅")
        st.rerun()
