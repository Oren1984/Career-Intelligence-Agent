# app/collectors/israel/drushim_collector.py
# This file defines the DrushimCollector class for scraping jobs from Drushim.co.il, Israel

"""
Drushim.co.il collector — Israel's largest mainstream job board.

STATUS: ENABLED (mock-safe)
Real scraping: NOT YET IMPLEMENTED — see TODOs below.

Drushim does not provide a public API. Real implementation requires
HTTP scraping of search results pages with BeautifulSoup or Playwright.

Mock behavior: returns hardcoded sample jobs for development/testing.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.collectors.base import RawJob
from app.collectors.israel.base_israel_collector import BaseIsraeliCollector

logger = logging.getLogger(__name__)

# Mock data — representative of what Drushim listings look like
_MOCK_DRUSHIM_JOBS = [
    {
        "id": "drushim-001",
        "title": "Python Developer",
        "company": "Startup IL",
        "city": "Tel Aviv",
        "description": (
            "Python developer needed for AI startup in Tel Aviv. "
            "Experience with FastAPI, Docker, and AWS required. "
            "Familiarity with ML frameworks is a strong advantage."
        ),
        "url": "https://www.drushim.co.il/job/1001",
        "days_ago": 1,
    },
    {
        "id": "drushim-002",
        "title": "AI Engineer",
        "company": "Israeli Tech Corp",
        "city": "Herzliya",
        "description": (
            "Seeking AI Engineer to develop LLM-based products. "
            "Python, RAG pipelines, and cloud deployment experience needed. "
            "Hybrid work from Herzliya office."
        ),
        "url": "https://www.drushim.co.il/job/1002",
        "days_ago": 2,
    },
    {
        "id": "drushim-003",
        "title": "MLOps Engineer",
        "company": "Scale8",
        "city": "Remote",
        "description": (
            "MLOps Engineer to manage model deployment, monitoring, and Terraform infrastructure. "
            "Docker and AWS required. Work from anywhere in Israel."
        ),
        "url": "https://www.drushim.co.il/job/1003",
        "days_ago": 3,
    },
]


class DrushimCollector(BaseIsraeliCollector):
    """
    Collector for Drushim.co.il — Israel's mainstream job board.

    Configuration (in sources.yaml):
        source_type: drushim
        search_query: "python developer"   # search term (used in real scraping)
        max_jobs: 50
        enabled: true

    Real scraping TODO:
        1. GET https://www.drushim.co.il/jobs/cat1/?q={search_query}
        2. Parse job listing cards with BeautifulSoup
        3. For each card: extract title, company, city, job_id, date
        4. GET individual job page for full description
        5. Return list of raw dicts
        6. Handle pagination (page param in URL)
        7. Respect rate limits — add sleep(1) between requests
    """

    source_name = "drushim"
    supports_apply_link = True
    requires_auth = False

    def __init__(self, search_query: str = "python", max_jobs: int = 50):
        self.search_query = search_query
        self.max_jobs = max_jobs

    def fetch_jobs(self) -> list[dict[str, Any]]:
        """
        Fetch jobs from Drushim.

        Current behavior: returns mock data (real scraping not implemented).

        TODO (real implementation):
            import requests
            from bs4 import BeautifulSoup
            url = f"https://www.drushim.co.il/jobs/cat1/?q={self.search_query}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(".job-item")  # selector TBD from actual page
            return [self._parse_card(card) for card in cards[:self.max_jobs]]
        """
        logger.info(
            "[drushim] fetch_jobs() — using mock data (real scraping not implemented)"
        )
        return _MOCK_DRUSHIM_JOBS[: self.max_jobs]

    def normalize_job(self, raw: dict[str, Any]) -> RawJob:
        """Convert a Drushim raw dict to a RawJob."""
        days_ago = raw.get("days_ago", 0)
        date_found = datetime.now(timezone.utc) - timedelta(days=days_ago)

        city = raw.get("city", "")
        location = f"{city}, Israel" if city and city.lower() != "remote" else city

        return RawJob(
            title=raw.get("title", ""),
            company=raw.get("company", ""),
            location=location,
            description=raw.get("description", ""),
            url=raw.get("url", ""),
            source=self.source_name,
            raw_text=raw.get("description", ""),
            date_found=date_found,
        )
