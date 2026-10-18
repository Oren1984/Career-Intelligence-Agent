# tests/test_dedup.py
# Part of the Career Intelligence Agent project.
"""Tests for deduplication logic."""
from app.collectors.base import RawJob
from app.db.normalizer import compute_hash, insert_jobs_dedup, raw_to_job
from app.db.models import Job


class TestComputeHash:
    def test_same_input_same_hash(self):
        h1 = compute_hash("AI Engineer", "TechCorp", "We need Python developers")
        h2 = compute_hash("AI Engineer", "TechCorp", "We need Python developers")
        assert h1 == h2

    def test_different_title_different_hash(self):
        h1 = compute_hash("AI Engineer", "TechCorp", "description")
        h2 = compute_hash("ML Engineer", "TechCorp", "description")
        assert h1 != h2

    def test_different_company_different_hash(self):
        h1 = compute_hash("AI Engineer", "CompanyA", "description")
        h2 = compute_hash("AI Engineer", "CompanyB", "description")
        assert h1 != h2

    def test_case_insensitive(self):
        h1 = compute_hash("AI Engineer", "TechCorp", "Description")
        h2 = compute_hash("ai engineer", "techcorp", "description")
        assert h1 == h2

    def test_returns_string(self):
        h = compute_hash("title", "company", "desc")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex


class TestInsertJobsDedup:
    def _make_raw(self, title="AI Engineer", company="Corp", description="Python AI job"):
        return RawJob(
            title=title,
            company=company,
            location="Remote",
            description=description,
            url="https://example.com/job/1",
            source="test",
        )

    def test_inserts_new_jobs(self, db_session):
        raw_jobs = [self._make_raw("Job A", "CompA"), self._make_raw("Job B", "CompB")]
        inserted, skipped = insert_jobs_dedup(db_session, raw_jobs)
        assert inserted == 2
        assert skipped == 0

    def test_skips_duplicates_same_batch(self, db_session):
        raw_jobs = [
            self._make_raw("Job A", "Corp"),
            self._make_raw("Job A", "Corp"),  # duplicate
        ]
        inserted, skipped = insert_jobs_dedup(db_session, raw_jobs)
        assert inserted == 1
        assert skipped == 1

    def test_skips_duplicates_across_batches(self, db_session):
        raw = self._make_raw("Job A", "Corp")
        insert_jobs_dedup(db_session, [raw])

        # Insert same job again
        inserted, skipped = insert_jobs_dedup(db_session, [raw])
        assert inserted == 0
        assert skipped == 1

    def test_total_records_in_db(self, db_session):
        raw_jobs = [self._make_raw(f"Job {i}", f"Corp {i}") for i in range(5)]
        insert_jobs_dedup(db_session, raw_jobs)
        count = db_session.query(Job).count()
        assert count == 5

    def test_raw_to_job_sets_hash(self):
        raw = self._make_raw()
        job = raw_to_job(raw)
        assert job.unique_hash
        assert len(job.unique_hash) == 64

    def test_raw_to_job_sets_status_new(self):
        raw = self._make_raw()
        job = raw_to_job(raw)
        assert job.status == "new"
