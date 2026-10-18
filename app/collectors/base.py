# collectors/base.py
# this file defines the BaseCollector abstract class
# and the RawJob dataclass for normalized job records.

"""Abstract base class for all job collectors."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


# Note: RawJob is a simple data structure to hold the raw information about
# a job listing before any processing or DB insertion.
@dataclass
class RawJob:
    """Normalized raw job record before DB insertion."""
    title: str
    company: str
    location: str
    description: str
    url: str
    source: str
    raw_text: str = ""
    date_found: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# BaseCollector defines the interface that all specific job collectors must implement.
class BaseCollector(ABC):
    """All collectors must implement collect()."""

    source_name: str = "unknown"

    @abstractmethod
    def collect(self) -> list[RawJob]:
        """Collect and return a list of raw job records."""
        ...
