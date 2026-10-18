# tests/test_israel_collectors.py
# Part of the Career Intelligence Agent project.
"""Tests for the Israeli job board collectors."""
import pytest
from datetime import datetime

from app.collectors.base import RawJob
from app.collectors.israel.base_israel_collector import BaseIsraeliCollector
from app.collectors.israel.drushim_collector import DrushimCollector
from app.collectors.israel.alljobs_collector import AllJobsCollector
from app.collectors.israel.jobnet_collector import JobNetCollector
from app.collectors.israel.jobkarov_collector import JobKarovCollector
from app.collectors.israel.jobmaster_collector import JobMasterCollector
from app.collectors.israel.jobify360_collector import Jobify360Collector


# ── Interface tests ────────────────────────────────────────────────────────────

class TestBaseIsraeliCollectorInterface:
    """Verify that concrete collectors implement the required interface."""

    def test_drushim_has_source_name(self):
        assert DrushimCollector.source_name == "drushim"

    def test_alljobs_has_source_name(self):
        assert AllJobsCollector.source_name == "alljobs"

    def test_drushim_supports_apply_link(self):
        c = DrushimCollector()
        assert isinstance(c.supports_apply_link, bool)

    def test_alljobs_supports_apply_link(self):
        c = AllJobsCollector()
        assert isinstance(c.supports_apply_link, bool)

    def test_country_is_il(self):
        for CollectorClass in [DrushimCollector, AllJobsCollector]:
            c = CollectorClass()
            assert c.country == "IL"

    def test_is_subclass_of_base_israel_collector(self):
        for CollectorClass in [DrushimCollector, AllJobsCollector]:
            assert issubclass(CollectorClass, BaseIsraeliCollector)

    def test_is_subclass_of_base_collector(self):
        from app.collectors.base import BaseCollector
        for CollectorClass in [DrushimCollector, AllJobsCollector]:
            assert issubclass(CollectorClass, BaseCollector)


# ── Drushim collector tests ────────────────────────────────────────────────────

class TestDrushimCollector:
    def test_collect_returns_list(self):
        c = DrushimCollector()
        jobs = c.collect()
        assert isinstance(jobs, list)

    def test_collect_returns_raw_jobs(self):
        c = DrushimCollector()
        jobs = c.collect()
        for job in jobs:
            assert isinstance(job, RawJob)

    def test_job_has_required_fields(self):
        c = DrushimCollector()
        jobs = c.collect()
        assert len(jobs) > 0
        job = jobs[0]
        assert job.title
        assert job.company
        assert job.url
        assert job.source == "drushim"

    def test_location_contains_israel(self):
        c = DrushimCollector()
        jobs = c.collect()
        # At least one non-remote job should have "Israel" in location
        non_remote = [j for j in jobs if "Remote" not in j.location]
        if non_remote:
            assert any("Israel" in j.location for j in non_remote)

    def test_date_found_is_datetime(self):
        c = DrushimCollector()
        jobs = c.collect()
        for job in jobs:
            assert isinstance(job.date_found, datetime)

    def test_max_jobs_respected(self):
        c = DrushimCollector(max_jobs=1)
        jobs = c.collect()
        assert len(jobs) <= 1

    def test_fetch_jobs_returns_list(self):
        c = DrushimCollector()
        raw = c.fetch_jobs()
        assert isinstance(raw, list)

    def test_normalize_job(self):
        c = DrushimCollector()
        raw = {"title": "Dev", "company": "Co", "city": "Tel Aviv",
               "url": "http://x.com", "description": "Test", "days_ago": 0}
        job = c.normalize_job(raw)
        assert isinstance(job, RawJob)
        assert job.title == "Dev"
        assert job.source == "drushim"


# ── AllJobs collector tests ────────────────────────────────────────────────────

class TestAllJobsCollector:
    def test_collect_returns_list(self):
        c = AllJobsCollector()
        jobs = c.collect()
        assert isinstance(jobs, list)

    def test_collect_returns_raw_jobs(self):
        c = AllJobsCollector()
        jobs = c.collect()
        for job in jobs:
            assert isinstance(job, RawJob)

    def test_job_source_is_alljobs(self):
        c = AllJobsCollector()
        jobs = c.collect()
        assert all(j.source == "alljobs" for j in jobs)

    def test_normalize_job(self):
        c = AllJobsCollector()
        raw = {"title": "Engineer", "company": "Corp", "city": "Haifa",
               "url": "http://y.com", "description": "Desc", "days_ago": 1}
        job = c.normalize_job(raw)
        assert isinstance(job, RawJob)
        assert "Israel" in job.location

    def test_max_jobs_respected(self):
        c = AllJobsCollector(max_jobs=2)
        jobs = c.collect()
        assert len(jobs) <= 2


# ── Disabled collectors: return empty list ─────────────────────────────────────

class TestDisabledCollectors:
    def test_jobnet_returns_empty(self):
        c = JobNetCollector()
        jobs = c.collect()
        assert jobs == []

    def test_jobkarov_returns_empty(self):
        c = JobKarovCollector()
        jobs = c.collect()
        assert jobs == []

    def test_jobmaster_returns_empty(self):
        c = JobMasterCollector()
        jobs = c.collect()
        assert jobs == []

    def test_jobify360_returns_empty(self):
        c = Jobify360Collector()
        jobs = c.collect()
        assert jobs == []

    def test_disabled_collectors_have_enabled_false(self):
        for CollectorClass in [JobNetCollector, JobKarovCollector, JobMasterCollector, Jobify360Collector]:
            assert CollectorClass.ENABLED is False

    def test_disabled_normalize_raises(self):
        for CollectorClass in [JobNetCollector, JobKarovCollector, JobMasterCollector, Jobify360Collector]:
            c = CollectorClass()
            with pytest.raises(NotImplementedError):
                c.normalize_job({})
