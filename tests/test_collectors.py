# tests/test_collectors.py
# Part of the Career Intelligence Agent project.
"""Tests for job collectors."""
from app.collectors.mock_collector import MockCollector
from app.collectors.base import RawJob


class TestMockCollector:
    def test_collect_returns_list(self):
        collector = MockCollector()
        jobs = collector.collect()
        assert isinstance(jobs, list)

    def test_collect_returns_raw_jobs(self):
        collector = MockCollector()
        jobs = collector.collect()
        assert len(jobs) > 0
        for job in jobs:
            assert isinstance(job, RawJob)

    def test_all_jobs_have_required_fields(self):
        collector = MockCollector()
        jobs = collector.collect()
        for job in jobs:
            assert job.title, f"Job missing title: {job}"
            assert job.company, f"Job missing company: {job}"
            assert job.description, f"Job missing description: {job}"
            assert job.url, f"Job missing url: {job}"
            assert job.source == "mock"

    def test_source_name_is_mock(self):
        collector = MockCollector()
        assert collector.source_name == "mock"

    def test_collect_returns_multiple_jobs(self):
        collector = MockCollector()
        jobs = collector.collect()
        assert len(jobs) >= 10, "Expected at least 10 mock jobs"

    def test_jobs_have_dates(self):
        collector = MockCollector()
        jobs = collector.collect()
        for job in jobs:
            assert job.date_found is not None
