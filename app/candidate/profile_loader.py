# candidate/profile_loader.py
# Defines CandidateProfile dataclass and load_candidate_profile function.

"""Candidate profile loader — reads structured profile files and builds a unified CandidateProfile."""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_PROFILE_DIR = Path(__file__).parent.parent.parent / "data" / "candidate_profile"
_CONFIG_PROFILE_PATH = Path(__file__).parent.parent.parent / "config" / "profile.yaml"


@dataclass
class CandidateProfile:
    """
    Unified candidate profile built from:
      - config/profile.yaml                  (roles, keywords, preferences, goals)
      - data/personal_profile.json           (personal overrides + new fields)
      - data/candidate_profile/summary.txt   (free-text summary)
      - data/candidate_profile/skills.json   (structured skills)
      - data/candidate_profile/projects.json (project examples)
    """

    # ── Personal Identity ────────────────────────────────────────────────────
    name: str = ""
    headline: str = ""

    # ── Core Role Targeting ──────────────────────────────────────────────────
    target_roles: list[str] = field(default_factory=list)
    preferred_role_track: str = ""
    experience_level: str = "mid"          # junior | mid | senior
    seniority_target: str = "mid"

    # ── Keywords ────────────────────────────────────────────────────────────
    positive_keywords: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)

    # ── Technologies ────────────────────────────────────────────────────────
    preferred_technologies: list[str] = field(default_factory=list)
    avoided_technologies: list[str] = field(default_factory=list)

    # ── Location & Work Mode ─────────────────────────────────────────────────
    preferred_locations: list[str] = field(default_factory=list)
    work_mode_preference: str = "any"      # remote | hybrid | onsite | any

    # ── Preferences ──────────────────────────────────────────────────────────
    company_type_preference: list[str] = field(default_factory=list)
    language_preference: str = "english"
    salary_preference: dict[str, Any] = field(default_factory=dict)

    # ── Career Direction ─────────────────────────────────────────────────────
    short_term_goal: str = ""
    long_term_goal: str = ""
    preferred_domains: list[str] = field(default_factory=list)
    willingness_to_learn: list[str] = field(default_factory=list)

    # ── Career Tracks ────────────────────────────────────────────────────────
    career_tracks: dict[str, Any] = field(default_factory=dict)

    # ── Personal Profile — explicit skill signals ─────────────────────────────
    strong_skills: list[str] = field(default_factory=list)
    # ^ Skills you are highly confident in (boost skill overlap scoring)
    weak_skills: list[str] = field(default_factory=list)
    # ^ Known weak areas (flagged in gap analysis even if technically "known")

    # ── Portfolio prioritisation ──────────────────────────────────────────────
    portfolio_project_priorities: list[str] = field(default_factory=list)
    # ^ Ordered project names — earlier = higher emphasis preference

    # ── Summaries ────────────────────────────────────────────────────────────
    resume_summary: str = ""
    achievements_summary: str = ""
    notes: str = ""

    # ── Profile Data Files ───────────────────────────────────────────────────
    summary: str = ""
    skills: dict[str, list[str]] = field(default_factory=dict)
    projects: list[dict[str, Any]] = field(default_factory=list)

    # ── Convenience Properties ───────────────────────────────────────────────

    @property
    def all_skills(self) -> list[str]:
        """Flat list of all skills: structured categories + strong_skills (deduplicated)."""
        result: list[str] = []
        for skill_list in self.skills.values():
            result.extend(skill_list)
        # Include strong_skills so they always count in skill matching
        for s in self.strong_skills:
            if s not in result:
                result.append(s)
        return result

    @property
    def all_skills_lower(self) -> list[str]:
        """Flat list of all skills, lowercased for matching."""
        return [s.lower() for s in self.all_skills]

    @property
    def preferred_technologies_lower(self) -> list[str]:
        return [t.lower() for t in self.preferred_technologies]

    @property
    def avoided_technologies_lower(self) -> list[str]:
        return [t.lower() for t in self.avoided_technologies]

    @property
    def all_portfolio_technologies(self) -> list[str]:
        """All unique technologies mentioned across all portfolio projects."""
        techs: list[str] = []
        for project in self.projects:
            techs.extend(project.get("technologies", []))
        return list(set(techs))

    @property
    def primary_track(self) -> str:
        """Primary career track from career_tracks config."""
        return self.career_tracks.get("primary", self.preferred_role_track or "")

    @property
    def acceptable_tracks(self) -> list[str]:
        return self.career_tracks.get("acceptable", [])

    @property
    def avoided_tracks(self) -> list[str]:
        return self.career_tracks.get("avoid", [])

    def to_prompt_string(self) -> str:
        """Build a concise profile summary suitable for LLM prompts."""
        parts: list[str] = []

        if self.summary:
            parts.append(f"Summary: {self.summary}")

        if self.target_roles:
            parts.append(f"Target Roles: {', '.join(self.target_roles)}")

        if self.all_skills:
            parts.append(f"Key Skills: {', '.join(self.all_skills[:20])}")
        elif self.positive_keywords:
            parts.append(f"Key Skills: {', '.join(self.positive_keywords)}")

        if self.projects:
            project_names = [p.get("name", "Unnamed") for p in self.projects[:3]]
            parts.append(f"Recent Projects: {', '.join(project_names)}")

        if self.short_term_goal:
            parts.append(f"Short-term Goal: {self.short_term_goal.strip()}")

        if self.preferred_domains:
            parts.append(f"Preferred Domains: {', '.join(self.preferred_domains)}")

        if self.negative_keywords:
            parts.append(f"Not targeting: {', '.join(self.negative_keywords)} roles")

        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            # Personal identity
            "name": self.name,
            "headline": self.headline,
            # Role targeting
            "target_roles": self.target_roles,
            "preferred_role_track": self.preferred_role_track,
            "experience_level": self.experience_level,
            "seniority_target": self.seniority_target,
            # Keywords
            "positive_keywords": self.positive_keywords,
            "negative_keywords": self.negative_keywords,
            # Technologies
            "preferred_technologies": self.preferred_technologies,
            "avoided_technologies": self.avoided_technologies,
            # Location
            "preferred_locations": self.preferred_locations,
            "work_mode_preference": self.work_mode_preference,
            # Preferences
            "company_type_preference": self.company_type_preference,
            "language_preference": self.language_preference,
            "salary_preference": self.salary_preference,
            # Goals
            "short_term_goal": self.short_term_goal,
            "long_term_goal": self.long_term_goal,
            "preferred_domains": self.preferred_domains,
            "willingness_to_learn": self.willingness_to_learn,
            "career_tracks": self.career_tracks,
            # Skills — flat list for scorer convenience
            "all_skills": self.all_skills,
            "strong_skills": self.strong_skills,
            "weak_skills": self.weak_skills,
            # Portfolio
            "portfolio_project_priorities": self.portfolio_project_priorities,
            "projects": self.projects,
            # Summaries
            "resume_summary": self.resume_summary,
            "achievements_summary": self.achievements_summary,
            "notes": self.notes,
            "summary": self.summary,
            # Raw skills dict
            "skills": self.skills,
        }


def load_candidate_profile(
    profile_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    personal_overlay: dict[str, Any] | None = None,
) -> CandidateProfile:
    """
    Load the candidate profile from disk.

    Reads (in order, all optional):
      1. config/profile.yaml              → base roles, keywords, preferences, goals
      2. data/personal_profile.json       → personal overrides + new fields
      3. data/candidate_profile/summary.txt   → free-text summary
      4. data/candidate_profile/skills.json   → structured skills
      5. data/candidate_profile/projects.json → projects

    Personal profile fields take priority over profile.yaml when non-empty.
    Missing files are silently skipped; defaults are empty.

    ``personal_overlay`` replaces step 2 with an overlay supplied by the caller
    (V2.0 stores it per workspace in PostgreSQL); when omitted the local
    data/personal_profile.json file is used as before.
    """
    profile = CandidateProfile()

    # 1. Load config/profile.yaml
    cfg_path = Path(config_path or _CONFIG_PROFILE_PATH)
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            profile.target_roles = cfg.get("target_roles", [])
            profile.positive_keywords = cfg.get("positive_keywords", [])
            profile.negative_keywords = cfg.get("negative_keywords", [])

            # New V2 fields
            profile.preferred_role_track = cfg.get("preferred_role_track", "")
            profile.experience_level = cfg.get("experience_level", "mid")
            profile.seniority_target = cfg.get("seniority_target", "mid")
            profile.preferred_technologies = cfg.get("preferred_technologies", [])
            profile.avoided_technologies = cfg.get("avoided_technologies", [])
            profile.preferred_locations = cfg.get("preferred_locations", [])
            profile.work_mode_preference = cfg.get("work_mode_preference", "any")
            profile.company_type_preference = cfg.get("company_type_preference", [])
            profile.language_preference = cfg.get("language_preference", "english")
            profile.salary_preference = cfg.get("salary_preference", {}) or {}
            profile.short_term_goal = cfg.get("short_term_goal", "")
            profile.long_term_goal = cfg.get("long_term_goal", "")
            profile.preferred_domains = cfg.get("preferred_domains", [])
            profile.willingness_to_learn = cfg.get("willingness_to_learn", [])
            profile.career_tracks = cfg.get("career_tracks", {}) or {}

            logger.debug("Loaded profile config from %s", cfg_path)
        except Exception as exc:
            logger.warning("Could not read %s: %s", cfg_path, exc)

    # 2. Overlay from data/personal_profile.json (personal overrides)
    try:
        if personal_overlay is not None:
            personal = personal_overlay
        else:
            from app.services.personal_profile_service import load_personal_profile
            personal = load_personal_profile()

        # Personal identity (new fields)
        if personal.get("name"):
            profile.name = personal["name"]
        if personal.get("headline"):
            profile.headline = personal["headline"]

        # Role targeting — override only if non-empty in personal profile
        if personal.get("target_roles"):
            profile.target_roles = personal["target_roles"]
        if personal.get("experience_level"):
            profile.experience_level = personal["experience_level"]
            profile.seniority_target = personal["experience_level"]
        if personal.get("work_mode_preference"):
            profile.work_mode_preference = personal["work_mode_preference"]
        if personal.get("preferred_locations"):
            profile.preferred_locations = personal["preferred_locations"]
        if personal.get("preferred_domains"):
            profile.preferred_domains = personal["preferred_domains"]

        # Skills
        if personal.get("strong_skills"):
            profile.strong_skills = personal["strong_skills"]
        if personal.get("weak_skills"):
            profile.weak_skills = personal["weak_skills"]
        if personal.get("willingness_to_learn"):
            profile.willingness_to_learn = personal["willingness_to_learn"]

        # Technologies
        if personal.get("preferred_technologies"):
            profile.preferred_technologies = personal["preferred_technologies"]
        if personal.get("avoided_technologies"):
            profile.avoided_technologies = personal["avoided_technologies"]

        # Goals
        if personal.get("short_term_goal"):
            profile.short_term_goal = personal["short_term_goal"]
        if personal.get("long_term_goal"):
            profile.long_term_goal = personal["long_term_goal"]

        # Career tracks
        ct = personal.get("career_tracks", {})
        if ct.get("primary"):
            profile.career_tracks = {**profile.career_tracks, **{k: v for k, v in ct.items() if v}}

        # Company & salary
        if personal.get("company_type_preference"):
            profile.company_type_preference = personal["company_type_preference"]
        sal = personal.get("salary_preference", {})
        if sal.get("min") or sal.get("currency"):
            profile.salary_preference = sal

        # Portfolio priorities
        if personal.get("portfolio_project_priorities"):
            profile.portfolio_project_priorities = personal["portfolio_project_priorities"]

        # Summaries
        if personal.get("resume_summary"):
            profile.resume_summary = personal["resume_summary"]
        if personal.get("achievements_summary"):
            profile.achievements_summary = personal["achievements_summary"]
        if personal.get("notes"):
            profile.notes = personal["notes"]

        logger.debug("Personal profile overlay applied from data/personal_profile.json")

    except ImportError:
        pass  # personal_profile_service not available
    except Exception as exc:
        logger.warning("Could not apply personal profile overlay: %s", exc)

    # 3–5. Load data/candidate_profile/ files
    p_dir = Path(profile_dir or _DEFAULT_PROFILE_DIR)

    summary_path = p_dir / "summary.txt"
    if summary_path.exists():
        try:
            profile.summary = summary_path.read_text(encoding="utf-8").strip()
            logger.debug("Loaded candidate summary from %s", summary_path)
        except Exception as exc:
            logger.warning("Could not read %s: %s", summary_path, exc)

    skills_path = p_dir / "skills.json"
    if skills_path.exists():
        try:
            with open(skills_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                profile.skills = data
            elif isinstance(data, list):
                profile.skills = {"skills": data}
            logger.debug("Loaded candidate skills from %s", skills_path)
        except Exception as exc:
            logger.warning("Could not read %s: %s", skills_path, exc)

    projects_path = p_dir / "projects.json"
    if projects_path.exists():
        try:
            with open(projects_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                profile.projects = data
            logger.debug("Loaded candidate projects from %s", projects_path)
        except Exception as exc:
            logger.warning("Could not read %s: %s", projects_path, exc)

    return profile
