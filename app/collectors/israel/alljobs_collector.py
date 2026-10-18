# app/collectors/israel/alljobs_collector.py
# This file defines the AllJobsCollector class for scraping jobs from AllJobs.co.il,

"""
AllJobs.co.il collector — Israel's second-largest job board.

STATUS: ENABLED (mock-safe)
Real scraping: NOT YET IMPLEMENTED — see TODOs below.

AllJobs does not provide a public API. Real implementation requires
HTTP scraping with BeautifulSoup or Playwright.

Mock behavior: returns hardcoded sample jobs for development/testing.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.collectors.base import RawJob
from app.collectors.israel.base_israel_collector import BaseIsraeliCollector

logger = logging.getLogger(__name__)

_MOCK_ALLJOBS_JOBS = [
    {
        "id": "alljobs-001",
        "title": "Full Stack Developer (Python + React)",
        "company": "FinTech IL",
        "city": "Ramat Gan",
        "description": (
            "Full stack developer for fintech startup. "
            "Python backend (FastAPI/Django), React frontend, Docker, AWS. "
            "2-5 years experience. Hybrid Tel Aviv area."
        ),
        "url": "https://www.alljobs.co.il/SingleJobInner.aspx?ID=1001",
        "days_ago": 1,
    },
    {
        "id": "alljobs-002",
        "title": "Data Engineer",
        "company": "DataOps Ltd",
        "city": "Beer Sheva",
        "description": (
            "Data Engineer to build pipelines and ETL flows. "
            "Python, SQL, Spark, and Airflow required. "
            "Experience with AWS or GCP is a plus."
        ),
        "url": "https://www.alljobs.co.il/SingleJobInner.aspx?ID=1002",
        "days_ago": 2,
    },
    {
        "id": "alljobs-003",
        "title": "Machine Learning Engineer",
        "company": "CyberSec AI",
        "city": "Tel Aviv",
        "description": (
            "ML Engineer to develop security-focused AI models. "
            "Python, scikit-learn, Docker. MLOps experience preferred. "
            "Office in Tel Aviv, 3 days on-site."
        ),
        "url": "https://www.alljobs.co.il/SingleJobInner.aspx?ID=1003",
        "days_ago": 4,
    },
]


class AllJobsCollector(BaseIsraeliCollector):
    """
    Collector for AllJobs.co.il.

    Configuration (in sources.yaml):
        source_type: alljobs
        search_query: "python"
        max_jobs: 50
        enabled: true

    Real scraping TODO:
        1. GET https://www.alljobs.co.il/SearchResultsGuest.aspx?q={search_query}
        2. Parse job listing rows with BeautifulSoup
        3. Extract: title, company, city, job ID, posted date from each row
        4. GET individual job page for full description
        5. Paginate: find next-page link and repeat
        6. Respect rate limits — add sleep(1) between pages
        7. Handle pagination and stop at max_jobs
    """

    source_name = "alljobs"
    supports_apply_link = True
    requires_auth = False

    def __init__(self, search_query: str = "python", max_jobs: int = 50):
        self.search_query = search_query
        self.max_jobs = max_jobs

    def fetch_jobs(self) -> list[dict[str, Any]]:
        """
        Fetch jobs from AllJobs.

        Current behavior: returns mock data (real scraping not implemented).

        TODO (real implementation):
            import requests
            from bs4 import BeautifulSoup
            url = f"https://www.alljobs.co.il/SearchResultsGuest.aspx?q={self.search_query}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select(".job-content")  # selector TBD from actual page
            return [self._parse_row(row) for row in rows[:self.max_jobs]]
        """
        logger.info(
            "[alljobs] fetch_jobs() — using mock data (real scraping not implemented)"
        )
        return _MOCK_ALLJOBS_JOBS[: self.max_jobs]

    def normalize_job(self, raw: dict[str, Any]) -> RawJob:
        """Convert an AllJobs raw dict to a RawJob."""
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
