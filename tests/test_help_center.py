"""Help Center content: both languages, required topics, contextual links, search, valid references."""
import re
from pathlib import Path

from dashboard.views.help_center import load_articles, search

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {"whats-new", "getting-started", "language", "modes", "jobs", "tracker", "dashboard",
            "search", "workspaces", "privacy", "backup", "faq"}


def test_both_languages_cover_the_same_required_topics():
    en = [a.topic for a in load_articles("en")]
    he = [a.topic for a in load_articles("he")]
    assert en == he
    assert REQUIRED <= set(en)
    assert len(en) == len(set(en))


def test_contextual_help_links_point_to_existing_topics():
    code = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "dashboard").rglob("*.py"))
    used = set(re.findall(r"""help_topic\s*=\s*["']([a-z0-9_-]+)["']""", code))
    assert used, "no contextual help links found"
    assert used <= {a.topic for a in load_articles("en")}


def test_search_in_both_languages():
    assert [a.topic for a in search(load_articles("en"), "pg_dump restore")] == ["backup"]
    assert "backup" in [a.topic for a in search(load_articles("he"), "גיבוי")]
    assert search(load_articles("en"), "zzzz-no-match") == []
    assert len(search(load_articles("en"), "")) == len(load_articles("en"))


def test_referenced_scripts_exist():
    text = (ROOT / "dashboard/help/en.md").read_text(encoding="utf-8") + (ROOT / "dashboard/help/he.md").read_text(encoding="utf-8")
    for script in set(re.findall(r"scripts/([a-z_]+\.py)", text)):
        assert (ROOT / "scripts" / script).exists(), script
