# collectors/greenhouse_collector.py
# this file defines the GreenhouseCollector class
# to fetch job listings from Greenhouse ATS public boards

"""
Greenhouse ATS collector.

Fetches public job listings from companies using the Greenhouse ATS.
No authentication required — uses the public boards API.

API endpoint: https://boards-api.greenhouse.io/v1/boards/{company}/jobs

Usage:
    collector = GreenhouseCollector(companies=["anthropic", "openai", "stripe"])
    jobs = collector.collect()

Each company slug is the identifier used in their Greenhouse board URL,
e.g. https://boards.greenhouse.io/anthropic → slug is "anthropic".
"""
import logging
from datetime import datetime, timezone
from typing import Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from app.collectors.base import BaseCollector, RawJob

logger = logging.getLogger(__name__)

_API_BASE = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
_REQUEST_TIMEOUT = 10  # seconds

# Default set of companies to query — expand as needed
DEFAULT_COMPANIES: list[str] = []


# Note: Greenhouse's public API does not require authentication for fetching job listings,
# but it does require the company slug. We rely on configuration to specify which companies to fetch from,
# as there is no central listing of all companies using Greenhouse.
class GreenhouseCollector(BaseCollector):
    """
    Collects jobs from Greenhouse ATS public boards.

    Args:
        companies: List of Greenhouse board slugs (e.g. ["anthropic", "stripe"]).
                   Configure in sources.yaml under greenhouse entries.
    """

    source_name = "greenhouse"

    def __init__(self, companies: list[str] | None = None):
        self.companies = companies or DEFAULT_COMPANIES

    def collect(self) -> list[RawJob]:
        if not HAS_REQUESTS:
            logger.warning("requests not installed — cannot collect Greenhouse jobs")
            return []

        if not self.companies:
            logger.info("GreenhouseCollector: no companies configured — returning empty")
            return []

        jobs: list[RawJob] = []
        for company in self.companies:
            try:
                fetched = self._fetch_company(company)
                jobs.extend(fetched)
                logger.info("Greenhouse[%s]: fetched %d jobs", company, len(fetched))
            except Exception as exc:
                logger.warning("Greenhouse[%s] failed: %s", company, exc)

        logger.info("GreenhouseCollector total: %d jobs", len(jobs))
        return jobs

    def _fetch_company(self, company: str) -> list[RawJob]:
        url = _API_BASE.format(company=company)
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        raw_jobs = data.get("jobs", [])
        return [self._parse_job(job, company) for job in raw_jobs if job.get("title")]

    def _parse_job(self, job: dict[str, Any], company: str) -> RawJob:
        title = job.get("title", "").strip()
        job_url = job.get("absolute_url", "")

        # Location: first office entry if present
        offices = job.get("offices", [])
        location = offices[0].get("name", "") if offices else ""

        # Department
        departments = job.get("departments", [])
        dept = departments[0].get("name", "") if departments else ""

        description = dept if dept else f"Role at {company.title()}"

        # updated_at if available, else now
        updated = job.get("updated_at", "")
        try:
            date_found = (
                datetime.fromisoformat(updated.replace("Z", "+00:00"))
                if updated
                else datetime.now(timezone.utc)
            )
        except Exception:
            date_found = datetime.now(timezone.utc)

        return RawJob(
            title=title,
            company=company.title(),
            location=location,
            description=description,
            url=job_url,
            source=f"greenhouse_{company}",
            raw_text=description,
            date_found=date_found,
        )
