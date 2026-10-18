# collectors/rss_collector.py
# this file defines the RSSCollector class to fetch jobs from RSS/Atom job feeds

"""RSS-based job collector. Fetches jobs from RSS/Atom job feeds."""
import logging
import re
from datetime import datetime, timezone
from typing import Any

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from app.collectors.base import BaseCollector, RawJob

logger = logging.getLogger(__name__)

# Public job RSS feeds — lightweight and free
DEFAULT_RSS_FEEDS = [
    {
        "url": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "source": "weworkremotely",
    },
    {
        "url": "https://remoteok.com/remote-jobs.rss",
        "source": "remoteok",
    },
]


# Note: RSS feeds are very unstructured and vary widely in format.
# We apply some heuristics to extract company/location/title,
# but we store the full description text for maximum context.
# The URL points to the original feed entry,
# which may be a job post on the company's site or a job board listing.
def _strip_html(html: str) -> str:
    """Remove HTML tags from text."""
    if not html:
        return ""
    if HAS_BS4:
        return BeautifulSoup(html, "lxml").get_text(separator=" ").strip()
    # Fallback: simple regex strip
    return re.sub(r"<[^>]+>", " ", html).strip()


def _parse_date(entry: Any) -> datetime:
    """Parse date from feed entry."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)  # feedparser *_parsed values are UTC
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _extract_company(entry: Any) -> str:
    """Try to extract company name from feed entry tags."""
    for attr in ("author", "dc_creator", "tags"):
        val = getattr(entry, attr, None)
        if isinstance(val, str) and val:
            return val.strip()
        if isinstance(val, list) and val:
            return val[0].get("term", "").strip()
    return ""


class RSSCollector(BaseCollector):
    """Collects jobs from a list of RSS/Atom feed URLs."""

    source_name = "rss"

    def __init__(self, feeds: list[dict] | None = None):
        self.feeds = feeds or DEFAULT_RSS_FEEDS

    def collect(self) -> list[RawJob]:
        if not HAS_FEEDPARSER:
            logger.warning("feedparser not installed — skipping RSS collection")
            return []

        jobs: list[RawJob] = []

        for feed_cfg in self.feeds:
            feed_url = feed_cfg["url"]
            source_label = feed_cfg.get("source", "rss")
            logger.info("Fetching RSS feed: %s", feed_url)

            try:
                feed = feedparser.parse(feed_url)
                entries = getattr(feed, "entries", [])
                logger.info("  → Found %d entries in %s", len(entries), feed_url)

                for entry in entries:
                    title = getattr(entry, "title", "") or ""
                    link = getattr(entry, "link", "") or ""
                    summary = getattr(entry, "summary", "") or ""
                    content_list = getattr(entry, "content", [])
                    content = content_list[0].get("value", "") if content_list else ""

                    description_html = content or summary
                    description = _strip_html(description_html)
                    company = _extract_company(entry)

                    # Try to get location from tags
                    location = ""
                    tags = getattr(entry, "tags", [])
                    if tags:
                        location = tags[0].get("term", "")

                    if not title:
                        continue

                    raw = RawJob(
                        title=title.strip(),
                        company=company,
                        location=location,
                        description=description,
                        url=link,
                        source=source_label,
                        raw_text=description,
                        date_found=_parse_date(entry),
                    )
                    jobs.append(raw)

            except Exception as exc:
                logger.warning("Failed to fetch feed %s: %s", feed_url, exc)

        logger.info("RSSCollector collected %d total jobs", len(jobs))
        return jobs
