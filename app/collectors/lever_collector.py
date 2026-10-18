# collectors/lever_collector.py
# this file defines the LeverCollector class

"""
Lever ATS collector.

Fetches public job postings from companies using the Lever ATS.
No authentication required — uses the public postings API.

API endpoint: https://api.lever.co/v0/postings/{company}

Usage:
    collector = LeverCollector(companies=["netflix", "github"])
    jobs = collector.collect()

Each company slug is the identifier used in their Lever board URL,
e.g. https://jobs.lever.co/netflix → slug is "netflix".
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

_API_BASE = "https://api.lever.co/v0/postings/{company}"
_REQUEST_TIMEOUT = 10  # seconds

DEFAULT_COMPANIES: list[str] = []


# Note: Lever's public API does not require authentication for fetching job postings,
# but it does require the company slug. We rely on configuration to specify which companies to fetch
class LeverCollector(BaseCollector):
    """
    Collects jobs from Lever ATS public boards.

    Args:
        companies: List of Lever posting slugs (e.g. ["netflix", "github"]).
                   Configure in sources.yaml under lever entries.
    """

    source_name = "lever"

    def __init__(self, companies: list[str] | None = None):
        self.companies = companies or DEFAULT_COMPANIES

    def collect(self) -> list[RawJob]:
        if not HAS_REQUESTS:
            logger.warning("requests not installed — cannot collect Lever jobs")
            return []

        if not self.companies:
            logger.info("LeverCollector: no companies configured — returning empty")
            return []

        jobs: list[RawJob] = []
        for company in self.companies:
            try:
                fetched = self._fetch_company(company)
                jobs.extend(fetched)
                logger.info("Lever[%s]: fetched %d jobs", company, len(fetched))
            except Exception as exc:
                logger.warning("Lever[%s] failed: %s", company, exc)

        logger.info("LeverCollector total: %d jobs", len(jobs))
        return jobs

    def _fetch_company(self, company: str) -> list[RawJob]:
        url = _API_BASE.format(company=company)
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return [self._parse_posting(p, company) for p in data if p.get("text")]

    def _parse_posting(self, posting: dict[str, Any], company: str) -> RawJob:
        title = posting.get("text", "").strip()
        posting_url = posting.get("hostedUrl", "") or posting.get("applyUrl", "")

        categories = posting.get("categories", {})
        all_locs = categories.get("allLocations")
        location = (
            categories.get("location", "")
            or (all_locs[0] if isinstance(all_locs, list) else "")
        )
        department = categories.get("team", "") or categories.get("department", "")

        # Build a short description from available metadata
        description_parts = []
        if department:
            description_parts.append(f"Team: {department}")
        if location:
            description_parts.append(f"Location: {location}")
        commitment = categories.get("commitment", "")
        if commitment:
            description_parts.append(f"Type: {commitment}")

        # Plain-text snippet from description list
        description_list = posting.get("description", {})
        if isinstance(description_list, dict):
            body = description_list.get("body", "")
            if body and isinstance(body, str):
                description_parts.append(body[:500])

        description = " | ".join(description_parts) if description_parts else f"Role at {company.title()}"

        # createdAt is a Unix ms timestamp
        created_ms = posting.get("createdAt", 0)
        try:
            date_found = (
                datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
                if created_ms
                else datetime.now(timezone.utc)
            )
        except Exception:
            date_found = datetime.now(timezone.utc)

        return RawJob(
            title=title,
            company=company.title(),
            location=location,
            description=description,
            url=posting_url,
            source=f"lever_{company}",
            raw_text=description,
            date_found=date_found,
        )
