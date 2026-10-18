# tests/test_candidate_profile.py
# Part of the Career Intelligence Agent project.
"""Tests for V2 candidate profile loader."""
import json
from pathlib import Path

from app.candidate.profile_loader import load_candidate_profile, CandidateProfile


class TestCandidateProfileLoader:
    def _make_profile_dir(self, tmp_path: Path, summary: str | None = None,
                          skills: dict | None = None, projects: list | None = None):
        """Helper: write candidate profile files into a temp directory."""
        if summary is not None:
            (tmp_path / "summary.txt").write_text(summary, encoding="utf-8")
        if skills is not None:
            (tmp_path / "skills.json").write_text(json.dumps(skills), encoding="utf-8")
        if projects is not None:
            (tmp_path / "projects.json").write_text(json.dumps(projects), encoding="utf-8")
        return tmp_path

    def _make_config(self, tmp_path: Path, data: dict) -> Path:
        import yaml
        cfg_path = tmp_path / "profile.yaml"
        cfg_path.write_text(yaml.dump(data), encoding="utf-8")
        return cfg_path

    def test_returns_candidate_profile_instance(self, tmp_path):
        result = load_candidate_profile(profile_dir=tmp_path)
        assert isinstance(result, CandidateProfile)

    def test_empty_dir_returns_defaults(self, tmp_path):
        result = load_candidate_profile(profile_dir=tmp_path)
        assert result.summary == ""
        assert result.skills == {}
        assert result.projects == []

    def test_loads_summary(self, tmp_path):
        self._make_profile_dir(tmp_path, summary="Experienced AI engineer")
        result = load_candidate_profile(profile_dir=tmp_path)
        assert result.summary == "Experienced AI engineer"

    def test_summary_stripped(self, tmp_path):
        self._make_profile_dir(tmp_path, summary="  hello  \n")
        result = load_candidate_profile(profile_dir=tmp_path)
        assert result.summary == "hello"

    def test_loads_skills_dict(self, tmp_path):
        skills = {"python": ["Python", "FastAPI"], "cloud": ["AWS"]}
        self._make_profile_dir(tmp_path, skills=skills)
        result = load_candidate_profile(profile_dir=tmp_path)
        assert result.skills == skills

    def test_loads_skills_list(self, tmp_path):
        skills = ["Python", "Docker", "AWS"]
        self._make_profile_dir(tmp_path, skills=skills)
        result = load_candidate_profile(profile_dir=tmp_path)
        assert result.skills == {"skills": skills}

    def test_loads_projects(self, tmp_path):
        projects = [
            {"name": "Project A", "description": "Cool project", "technologies": ["Python"]}
        ]
        self._make_profile_dir(tmp_path, projects=projects)
        result = load_candidate_profile(profile_dir=tmp_path)
        assert len(result.projects) == 1
        assert result.projects[0]["name"] == "Project A"

    def test_all_skills_flat_list(self, tmp_path):
        skills = {"a": ["Python", "Docker"], "b": ["AWS"]}
        self._make_profile_dir(tmp_path, skills=skills)
        result = load_candidate_profile(profile_dir=tmp_path)
        assert set(result.all_skills) == {"Python", "Docker", "AWS"}

    def test_all_skills_empty_when_no_skills(self, tmp_path):
        result = load_candidate_profile(profile_dir=tmp_path)
        assert result.all_skills == []

    def test_loads_config_profile_yaml(self, tmp_path):
        data = {
            "target_roles": ["AI Engineer"],
            "positive_keywords": ["python", "ai"],
            "negative_keywords": ["senior"],
        }
        cfg = self._make_config(tmp_path, data)
        result = load_candidate_profile(profile_dir=tmp_path, config_path=cfg)
        assert result.target_roles == ["AI Engineer"]
        assert "python" in result.positive_keywords
        assert "senior" in result.negative_keywords

    def test_to_prompt_string_non_empty(self, tmp_path):
        self._make_profile_dir(
            tmp_path,
            summary="Senior AI engineer",
            skills={"python": ["Python"]},
        )
        cfg_data = {"target_roles": ["AI Engineer"], "positive_keywords": ["python"], "negative_keywords": []}
        cfg = self._make_config(tmp_path, cfg_data)
        result = load_candidate_profile(profile_dir=tmp_path, config_path=cfg)
        prompt = result.to_prompt_string()
        assert len(prompt) > 0
        assert "AI Engineer" in prompt

    def test_to_prompt_string_contains_summary(self, tmp_path):
        self._make_profile_dir(tmp_path, summary="Expert in LLM systems")
        result = load_candidate_profile(profile_dir=tmp_path)
        prompt = result.to_prompt_string()
        assert "Expert in LLM systems" in prompt

    def test_to_prompt_string_contains_skills(self, tmp_path):
        self._make_profile_dir(tmp_path, skills={"python": ["Python", "FastAPI"]})
        result = load_candidate_profile(profile_dir=tmp_path)
        prompt = result.to_prompt_string()
        assert "Python" in prompt or "FastAPI" in prompt

    def test_to_dict_has_required_keys(self, tmp_path):
        result = load_candidate_profile(profile_dir=tmp_path)
        d = result.to_dict()
        for key in ["target_roles", "positive_keywords", "negative_keywords", "summary", "skills", "projects"]:
            assert key in d

    def test_graceful_on_invalid_json(self, tmp_path):
        (tmp_path / "skills.json").write_text("not valid json {{", encoding="utf-8")
        # Should not raise; just use defaults
        result = load_candidate_profile(profile_dir=tmp_path)
        assert result.skills == {}

    def test_projects_not_list_ignored(self, tmp_path):
        (tmp_path / "projects.json").write_text('{"not": "a list"}', encoding="utf-8")
        result = load_candidate_profile(profile_dir=tmp_path)
        assert result.projects == []

    def test_missing_config_uses_defaults(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        result = load_candidate_profile(profile_dir=tmp_path, config_path=missing)
        assert result.target_roles == []
        assert result.positive_keywords == []
