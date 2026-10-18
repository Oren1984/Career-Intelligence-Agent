# tests/test_new_collectors.py
# Part of the Career Intelligence Agent project.
"""Tests for V2.5 collectors — Greenhouse, Lever, HackerNews."""
from unittest.mock import patch, MagicMock

from app.collectors.base import RawJob


# ── GreenhouseCollector ────────────────────────────────────────────────────────

class TestGreenhouseCollector:
    def test_import(self):
        from app.collectors.greenhouse_collector import GreenhouseCollector
        assert GreenhouseCollector is not None

    def test_source_name(self):
        from app.collectors.greenhouse_collector import GreenhouseCollector
        assert GreenhouseCollector.source_name == "greenhouse"

    def test_empty_companies_returns_empty(self):
        from app.collectors.greenhouse_collector import GreenhouseCollector
        c = GreenhouseCollector(companies=[])
        result = c.collect()
        assert result == []

    def test_returns_list_of_rawjob(self):
        from app.collectors.greenhouse_collector import GreenhouseCollector

        mock_response = {
            "jobs": [
                {
                    "title": "AI Engineer",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                    "offices": [{"name": "Remote"}],
                    "departments": [{"name": "Engineering"}],
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status.return_value = None

        with patch("app.collectors.greenhouse_collector.requests.get", return_value=mock_resp):
            c = GreenhouseCollector(companies=["acme"])
            result = c.collect()

        assert len(result) == 1
        assert isinstance(result[0], RawJob)

    def test_job_fields_populated(self):
        from app.collectors.greenhouse_collector import GreenhouseCollector

        mock_response = {
            "jobs": [
                {
                    "title": "ML Engineer",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
                    "offices": [{"name": "New York, NY"}],
                    "departments": [{"name": "AI Team"}],
                    "updated_at": "",
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status.return_value = None

        with patch("app.collectors.greenhouse_collector.requests.get", return_value=mock_resp):
            c = GreenhouseCollector(companies=["acme"])
            result = c.collect()

        job = result[0]
        assert job.title == "ML Engineer"
        assert job.url == "https://boards.greenhouse.io/acme/jobs/42"
        assert job.location == "New York, NY"
        assert "greenhouse" in job.source

    def test_failed_company_skipped(self):
        from app.collectors.greenhouse_collector import GreenhouseCollector
        import requests as req

        with patch("app.collectors.greenhouse_collector.requests.get", side_effect=req.RequestException("timeout")):
            c = GreenhouseCollector(companies=["failing-company"])
            result = c.collect()

        assert result == []

    def test_jobs_without_title_skipped(self):
        from app.collectors.greenhouse_collector import GreenhouseCollector

        mock_response = {"jobs": [{"title": "", "absolute_url": "http://x.com"}]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status.return_value = None

        with patch("app.collectors.greenhouse_collector.requests.get", return_value=mock_resp):
            c = GreenhouseCollector(companies=["acme"])
            result = c.collect()

        assert result == []

    def test_multiple_companies(self):
        from app.collectors.greenhouse_collector import GreenhouseCollector

        def mock_get(url, timeout):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = {
                "jobs": [{"title": "Engineer", "absolute_url": url, "offices": [], "departments": []}]
            }
            return resp

        with patch("app.collectors.greenhouse_collector.requests.get", side_effect=mock_get):
            c = GreenhouseCollector(companies=["acme", "beta"])
            result = c.collect()

        assert len(result) == 2


# ── LeverCollector ─────────────────────────────────────────────────────────────

class TestLeverCollector:
    def test_import(self):
        from app.collectors.lever_collector import LeverCollector
        assert LeverCollector is not None

    def test_source_name(self):
        from app.collectors.lever_collector import LeverCollector
        assert LeverCollector.source_name == "lever"

    def test_empty_companies_returns_empty(self):
        from app.collectors.lever_collector import LeverCollector
        c = LeverCollector(companies=[])
        result = c.collect()
        assert result == []

    def test_returns_list_of_rawjob(self):
        from app.collectors.lever_collector import LeverCollector

        mock_data = [
            {
                "text": "Senior AI Engineer",
                "hostedUrl": "https://jobs.lever.co/acme/abc123",
                "categories": {
                    "location": "Remote",
                    "team": "Engineering",
                    "commitment": "Full-time",
                },
                "createdAt": 1700000000000,
            }
        ]

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status.return_value = None

        with patch("app.collectors.lever_collector.requests.get", return_value=mock_resp):
            c = LeverCollector(companies=["acme"])
            result = c.collect()

        assert len(result) == 1
        assert isinstance(result[0], RawJob)

    def test_job_fields_populated(self):
        from app.collectors.lever_collector import LeverCollector

        mock_data = [
            {
                "text": "MLOps Engineer",
                "hostedUrl": "https://jobs.lever.co/corp/xyz",
                "categories": {"location": "Berlin", "team": "ML Platform"},
                "createdAt": 1700000000000,
            }
        ]

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status.return_value = None

        with patch("app.collectors.lever_collector.requests.get", return_value=mock_resp):
            c = LeverCollector(companies=["corp"])
            result = c.collect()

        job = result[0]
        assert job.title == "MLOps Engineer"
        assert job.url == "https://jobs.lever.co/corp/xyz"
        assert "lever" in job.source

    def test_failed_company_skipped(self):
        from app.collectors.lever_collector import LeverCollector
        import requests as req

        with patch("app.collectors.lever_collector.requests.get", side_effect=req.RequestException("err")):
            c = LeverCollector(companies=["fail"])
            result = c.collect()

        assert result == []

    def test_entries_without_text_skipped(self):
        from app.collectors.lever_collector import LeverCollector

        mock_data = [{"text": "", "hostedUrl": "http://x.com", "categories": {}}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status.return_value = None

        with patch("app.collectors.lever_collector.requests.get", return_value=mock_resp):
            c = LeverCollector(companies=["acme"])
            result = c.collect()

        assert result == []

    def test_date_from_timestamp(self):
        from app.collectors.lever_collector import LeverCollector

        mock_data = [{"text": "Dev", "hostedUrl": "http://x.com", "categories": {}, "createdAt": 1700000000000}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status.return_value = None

        with patch("app.collectors.lever_collector.requests.get", return_value=mock_resp):
            c = LeverCollector(companies=["co"])
            result = c.collect()

        assert result[0].date_found is not None


# ── HackerNewsHiringCollector ──────────────────────────────────────────────────

class TestHackerNewsHiringCollector:
    def test_import(self):
        from app.collectors.hackernews_collector import HackerNewsHiringCollector
        assert HackerNewsHiringCollector is not None

    def test_source_name(self):
        from app.collectors.hackernews_collector import HackerNewsHiringCollector
        assert HackerNewsHiringCollector.source_name == "hackernews_hiring"

    def test_no_story_returns_empty(self):
        from app.collectors.hackernews_collector import HackerNewsHiringCollector

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"hits": []}
        mock_resp.raise_for_status.return_value = None

        with patch("app.collectors.hackernews_collector.requests.get", return_value=mock_resp):
            c = HackerNewsHiringCollector()
            result = c.collect()

        assert result == []

    def test_returns_list_of_rawjob(self):
        from app.collectors.hackernews_collector import HackerNewsHiringCollector

        story_resp = {"hits": [{"objectID": "999", "title": "Ask HN: Who is Hiring? (March 2026)"}]}
        comments_resp = {
            "hits": [
                {
                    "objectID": "1001",
                    "comment_text": (
                        "Acme Corp | AI Engineer | Remote | Python, LLM, RAG, Docker | "
                        "We are building LLM-based products. Apply at jobs.acme.com."
                    ),
                    "created_at": "2026-03-01T10:00:00Z",
                }
            ]
        }

        responses = [story_resp, comments_resp]
        call_count = [0]

        def mock_get(url, params=None, timeout=None):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("app.collectors.hackernews_collector.requests.get", side_effect=mock_get):
            c = HackerNewsHiringCollector()
            result = c.collect()

        assert len(result) >= 1
        assert isinstance(result[0], RawJob)

    def test_rawjob_fields(self):
        from app.collectors.hackernews_collector import HackerNewsHiringCollector

        story_resp = {"hits": [{"objectID": "42", "title": "Ask HN: Who is Hiring? (Jan 2026)"}]}
        comments_resp = {
            "hits": [
                {
                    "objectID": "500",
                    "comment_text": (
                        "TechCo | Backend Engineer | Remote | "
                        "Python, Docker, AWS required. Full-time position."
                    ),
                    "created_at": "2026-01-15T00:00:00Z",
                }
            ]
        }

        responses = [story_resp, comments_resp]
        call_count = [0]

        def mock_get(url, params=None, timeout=None):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("app.collectors.hackernews_collector.requests.get", side_effect=mock_get):
            c = HackerNewsHiringCollector()
            result = c.collect()

        assert len(result) >= 1
        job = result[0]
        assert job.source == "hackernews_hiring"
        assert "ycombinator" in job.url
        assert len(job.description) > 0

    def test_short_comments_filtered(self):
        from app.collectors.hackernews_collector import HackerNewsHiringCollector

        story_resp = {"hits": [{"objectID": "1", "title": "Ask HN: Who is Hiring?"}]}
        comments_resp = {
            "hits": [
                {"objectID": "2", "comment_text": "short", "created_at": "2026-01-01T00:00:00Z"},
            ]
        }

        responses = [story_resp, comments_resp]
        call_count = [0]

        def mock_get(url, params=None, timeout=None):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("app.collectors.hackernews_collector.requests.get", side_effect=mock_get):
            c = HackerNewsHiringCollector()
            result = c.collect()

        assert result == []

    def test_max_jobs_respected(self):
        from app.collectors.hackernews_collector import HackerNewsHiringCollector

        story_resp = {"hits": [{"objectID": "1", "title": "Ask HN: Who is Hiring?"}]}
        comment_text = (
            "Acme Corp | ML Engineer | Remote | Python, Docker, LLM, RAG. "
            "Full-time. We build AI products. Apply at acme.com/careers."
        )
        comments_resp = {
            "hits": [
                {"objectID": str(i), "comment_text": comment_text, "created_at": "2026-01-01T00:00:00Z"}
                for i in range(20)
            ]
        }

        responses = [story_resp, comments_resp]
        call_count = [0]

        def mock_get(url, params=None, timeout=None):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("app.collectors.hackernews_collector.requests.get", side_effect=mock_get):
            c = HackerNewsHiringCollector(max_jobs=5)
            result = c.collect()

        assert len(result) <= 5

    def test_network_error_returns_empty(self):
        from app.collectors.hackernews_collector import HackerNewsHiringCollector
        import requests as req

        with patch("app.collectors.hackernews_collector.requests.get", side_effect=req.RequestException("err")):
            c = HackerNewsHiringCollector()
            result = c.collect()

        assert result == []


# ── source_loader integration ──────────────────────────────────────────────────

class TestSourceLoaderNewTypes:
    def test_greenhouse_type_loads_collector(self, tmp_path):
        import yaml
        from app.collectors.source_loader import load_collectors
        from app.collectors.greenhouse_collector import GreenhouseCollector

        config = {
            "sources": [
                {
                    "name": "test_greenhouse",
                    "enabled": True,
                    "source_type": "greenhouse",
                    "companies": ["acme"],
                    "priority": 5,
                }
            ]
        }
        cfg_path = tmp_path / "sources.yaml"
        cfg_path.write_text(yaml.dump(config), encoding="utf-8")

        collectors = load_collectors(path=str(cfg_path), include_mock=False)
        assert len(collectors) == 1
        assert isinstance(collectors[0], GreenhouseCollector)

    def test_lever_type_loads_collector(self, tmp_path):
        import yaml
        from app.collectors.source_loader import load_collectors
        from app.collectors.lever_collector import LeverCollector

        config = {
            "sources": [
                {
                    "name": "test_lever",
                    "enabled": True,
                    "source_type": "lever",
                    "companies": ["netflix"],
                    "priority": 5,
                }
            ]
        }
        cfg_path = tmp_path / "sources.yaml"
        cfg_path.write_text(yaml.dump(config), encoding="utf-8")

        collectors = load_collectors(path=str(cfg_path), include_mock=False)
        assert len(collectors) == 1
        assert isinstance(collectors[0], LeverCollector)

    def test_hackernews_type_loads_collector(self, tmp_path):
        import yaml
        from app.collectors.source_loader import load_collectors
        from app.collectors.hackernews_collector import HackerNewsHiringCollector

        config = {
            "sources": [
                {
                    "name": "hackernews",
                    "enabled": True,
                    "source_type": "hackernews",
                    "max_jobs": 50,
                    "priority": 5,
                }
            ]
        }
        cfg_path = tmp_path / "sources.yaml"
        cfg_path.write_text(yaml.dump(config), encoding="utf-8")

        collectors = load_collectors(path=str(cfg_path), include_mock=False)
        assert len(collectors) == 1
        assert isinstance(collectors[0], HackerNewsHiringCollector)
        assert collectors[0].max_jobs == 50

    def test_greenhouse_no_companies_skipped(self, tmp_path):
        import yaml
        from app.collectors.source_loader import load_collectors

        config = {
            "sources": [
                {
                    "name": "greenhouse_empty",
                    "enabled": True,
                    "source_type": "greenhouse",
                    "companies": [],
                    "priority": 5,
                }
            ]
        }
        cfg_path = tmp_path / "sources.yaml"
        cfg_path.write_text(yaml.dump(config), encoding="utf-8")

        collectors = load_collectors(path=str(cfg_path), include_mock=False)
        assert len(collectors) == 0

    def test_disabled_new_sources_excluded(self, tmp_path):
        import yaml
        from app.collectors.source_loader import load_collectors

        config = {
            "sources": [
                {
                    "name": "greenhouse_off",
                    "enabled": False,
                    "source_type": "greenhouse",
                    "companies": ["acme"],
                    "priority": 5,
                }
            ]
        }
        cfg_path = tmp_path / "sources.yaml"
        cfg_path.write_text(yaml.dump(config), encoding="utf-8")

        collectors = load_collectors(path=str(cfg_path), include_mock=False)
        assert len(collectors) == 0
