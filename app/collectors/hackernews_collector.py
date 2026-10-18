# collectors/hackernews_collector.py
# this file defines the HackerNewsHiringCollector class
# to fetch job listings from the monthly "Ask HN: Who is Hiring?" thread

"""
Hacker News "Who is Hiring?" collector.

Finds the latest monthly "Ask HN: Who is Hiring?" story and collects
job comments from it using the Algolia HN Search API.

APIs used:
  1. Find story: https://hn.algolia.com/api/v1/search?query=who+is+hiring&tags=story
  2. Fetch comments: https://hn.algolia.com/api/v1/search?tags=comment,story_{id}&hitsPerPage=200

No authentication required. Public API.

Usage:
    collector = HackerNewsHiringCollector(max_jobs=100)
    jobs = collector.collect()

Note: Comments are plain-text job ads posted by companies/individuals. The format is
      inconsistent — parsing extracts what it can and stores the full comment as description.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from app.collectors.base import BaseCollector, RawJob

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
_REQUEST_TIMEOUT = 15
_HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"

# Patterns to extract structured info from HN job comments
_REMOTE_PATTERN = re.compile(r"\bremote\b", re.IGNORECASE)
_LOCATION_PATTERN = re.compile(
    r"(?:location|office|based)[:\s]+([A-Z][a-zA-Z ,]+?)(?:\||$|\n|\()", re.IGNORECASE
)
_COMPANY_PATTERN = re.compile(r"^([A-Z][A-Za-z0-9 &.,'-]{1,60})\s*[|\-–]", re.MULTILINE)
_TITLE_PATTERN = re.compile(
    r"\b(engineer|developer|scientist|architect|manager|designer|"
    r"analyst|lead|director|intern|ml|ai|llm|mlops|backend|frontend|"
    r"fullstack|full.stack|data|platform|devops|sre|cloud)\b",
    re.IGNORECASE,
)


# Note: HN job posts are very unstructured. We apply some heuristics to extract company/location/title,
# but we store the full comment text as the description for maximum context.
# The URL points to the HN comment itself.
class HackerNewsHiringCollector(BaseCollector):
    """
    Collects jobs from the HN "Who is Hiring?" monthly thread.

    Args:
        max_jobs: Maximum number of job comments to return (default: 100).
    """

    source_name = "hackernews_hiring"

    def __init__(self, max_jobs: int = 100):
        self.max_jobs = max_jobs

    def collect(self) -> list[RawJob]:
        if not HAS_REQUESTS:
            logger.warning("requests not installed — cannot collect HN jobs")
            return []

        try:
            story_id = self._find_latest_hiring_story()
            if not story_id:
                logger.warning("HackerNewsHiringCollector: no 'Who is Hiring?' story found")
                return []
            logger.info("HN hiring story ID: %s", story_id)
            return self._fetch_comments(story_id)
        except Exception as exc:
            logger.warning("HackerNewsHiringCollector failed: %s", exc)
            return []

    # We search for the most recent "Ask HN: Who is Hiring?" story using the Algolia API,
    # which allows us to find it even if it's not on the first page of HN.
    def _find_latest_hiring_story(self) -> str | None:
        """Find the most recent 'Ask HN: Who is Hiring?' story."""
        params = {
            "query": "Ask HN: Who is Hiring?",
            "tags": "story",
            "hitsPerPage": 5,
        }
        resp = requests.get(_SEARCH_URL, params=params, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])

        for hit in hits:
            title = hit.get("title", "")
            if "who is hiring" in title.lower():
                return str(hit.get("objectID", ""))

        return None

    # Note: We fetch comments using the Algolia API, which returns them in a structured format.
    # We then apply heuristics to parse out company/location/title,
    # but we keep the full comment text as the description for maximum context.
    def _fetch_comments(self, story_id: str) -> list[RawJob]:
        """Fetch job comments from the hiring thread."""
        params = {
            "tags": f"comment,story_{story_id}",
            "hitsPerPage": min(self.max_jobs, 200),
        }
        resp = requests.get(_SEARCH_URL, params=params, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])

        jobs: list[RawJob] = []
        for hit in hits:
            job = self._parse_comment(hit)
            if job:
                jobs.append(job)

        logger.info("HackerNewsHiringCollector: parsed %d jobs from %d comments", len(jobs), len(hits))
        return jobs[: self.max_jobs]

    # The parsing is very heuristic and best-effort. HN job posts are notoriously unstructured,
    # so we look for common patterns but fall back to defaults when we can't find structured info.
    def _parse_comment(self, hit: dict[str, Any]) -> RawJob | None:
        """Parse a HN comment into a RawJob. Returns None if it looks like spam/noise."""
        text = hit.get("comment_text", "") or ""
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", text).strip()

        if len(text) < 50:
            return None  # too short to be a real job post

        # Require at least a hint of a tech/engineering role
        if not _TITLE_PATTERN.search(text):
            return None

        comment_id = hit.get("objectID", "")
        url = _HN_ITEM_URL.format(id=comment_id)

        # Try to extract company name
        company = ""
        m = _COMPANY_PATTERN.search(text)
        if m:
            company = m.group(1).strip()

        # Build a synthetic title from the first meaningful line
        first_line = text.split("\n")[0][:120].strip()
        title = first_line if first_line else "HN Job Posting"

        # Location
        location = "Remote" if _REMOTE_PATTERN.search(text) else ""
        m = _LOCATION_PATTERN.search(text)
        if m:
            loc_candidate = m.group(1).strip()
            if location and loc_candidate:
                location = f"{loc_candidate} (Remote OK)"
            elif loc_candidate:
                location = loc_candidate

        # Date
        created_at = hit.get("created_at", "")
        try:
            date_found = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else datetime.now(timezone.utc)
        except Exception:
            date_found = datetime.now(timezone.utc)

        return RawJob(
            title=title,
            company=company or "HN Poster",
            location=location,
            description=text[:1000],
            url=url,
            source="hackernews_hiring",
            raw_text=text,
            date_found=date_found,
        )
