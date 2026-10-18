# tests/test_dedup_engine.py
# Part of the Career Intelligence Agent project.
"""Tests for the layered deduplication engine."""
from dataclasses import dataclass

from app.dedup.dedup_engine import DedupEngine, DedupResult, _normalize_text, _url_key


# ── Helpers ────────────────────────────────────────────────────────────────────

@dataclass
class MockJob:
    """Minimal job-like object for dedup tests."""
    title: str
    company: str
    location: str = ""
    url: str = ""
    source: str = "test"
    source_job_id: str = ""


def make_job(title="Python Dev", company="Acme", location="Tel Aviv",
             url="http://example.com/1", source="test", source_job_id=""):
    return MockJob(title=title, company=company, location=location,
                   url=url, source=source, source_job_id=source_job_id)


# ── Unit: helper functions ─────────────────────────────────────────────────────

class TestHelpers:
    def test_normalize_text_lowercase(self):
        assert _normalize_text("  Python Dev  ") == "python dev"

    def test_normalize_text_punctuation_removed(self):
        result = _normalize_text("Python/Dev (Senior)")
        assert "/" not in result
        assert "(" not in result

    def test_url_key_strips_slash(self):
        assert _url_key("http://example.com/") == "http://example.com"

    def test_url_key_lowercase(self):
        assert _url_key("HTTP://EXAMPLE.COM") == "http://example.com"


# ── DedupEngine: URL layer ─────────────────────────────────────────────────────

class TestDedupEngineURL:
    def test_same_url_is_duplicate(self):
        engine = DedupEngine(enable_fuzzy=False)
        job1 = make_job(url="http://example.com/1")
        job2 = make_job(title="Different Title", url="http://example.com/1")
        engine.add(job1)
        is_dup, reason = engine.is_duplicate(job2)
        assert is_dup is True
        assert reason == "url"

    def test_different_url_not_duplicate(self):
        engine = DedupEngine(enable_fuzzy=False)
        job1 = make_job(title="Python Dev", company="Acme", location="Tel Aviv", url="http://example.com/1")
        # Different title/company/location so fingerprint also differs
        job2 = make_job(title="Java Dev", company="BetaCorp", location="Haifa", url="http://example.com/2")
        engine.add(job1)
        is_dup, reason = engine.is_duplicate(job2)
        assert is_dup is False

    def test_url_trailing_slash_deduped(self):
        engine = DedupEngine(enable_fuzzy=False)
        job1 = make_job(url="http://example.com/job/1/")
        job2 = make_job(url="http://example.com/job/1")
        engine.add(job1)
        is_dup, reason = engine.is_duplicate(job2)
        assert is_dup is True


# ── DedupEngine: source_id layer ──────────────────────────────────────────────

class TestDedupEngineSourceId:
    def test_same_source_id_is_duplicate(self):
        engine = DedupEngine(enable_fuzzy=False)
        job1 = make_job(url="", source="drushim", source_job_id="abc123")
        job2 = make_job(url="", title="Different", source="drushim", source_job_id="abc123")
        engine.add(job1)
        is_dup, reason = engine.is_duplicate(job2)
        assert is_dup is True
        assert reason == "source_id"

    def test_different_source_same_id_not_duplicate(self):
        engine = DedupEngine(enable_fuzzy=False)
        # Different source+id AND different title/company/location so fingerprint differs too
        job1 = make_job(title="Python Dev", company="Acme", location="Tel Aviv",
                        url="", source="drushim", source_job_id="123")
        job2 = make_job(title="Java Dev", company="BetaCorp", location="Haifa",
                        url="", source="alljobs", source_job_id="123")
        engine.add(job1)
        is_dup, reason = engine.is_duplicate(job2)
        assert is_dup is False


# ── DedupEngine: fingerprint layer ────────────────────────────────────────────

class TestDedupEngineFingerprint:
    def test_same_title_company_city_is_duplicate(self):
        engine = DedupEngine(enable_fuzzy=False)
        job1 = make_job(title="Python Dev", company="Acme", location="Tel Aviv", url="")
        job2 = make_job(title="Python Dev", company="Acme", location="Tel Aviv", url="http://different-url.com")
        engine.add(job1)
        is_dup, reason = engine.is_duplicate(job2)
        assert is_dup is True
        assert reason == "fingerprint"

    def test_different_company_not_duplicate(self):
        engine = DedupEngine(enable_fuzzy=False)
        job1 = make_job(title="Python Dev", company="Acme", location="Tel Aviv", url="")
        job2 = make_job(title="Python Dev", company="BetaCorp", location="Tel Aviv", url="")
        engine.add(job1)
        is_dup, reason = engine.is_duplicate(job2)
        assert is_dup is False


# ── DedupEngine: deduplicate batch ────────────────────────────────────────────

class TestDedupEngineBatch:
    def test_dedup_removes_exact_url_duplicates(self):
        engine = DedupEngine(enable_fuzzy=False)
        jobs = [
            make_job(title="Job A", url="http://x.com/1"),
            make_job(title="Job A copy", url="http://x.com/1"),  # dup
            make_job(title="Job B", url="http://x.com/2"),
        ]
        unique, result = engine.deduplicate(jobs)
        assert len(unique) == 2
        assert result.duplicate_count == 1
        assert result.duplicates_by_url == 1

    def test_dedup_result_counts(self):
        engine = DedupEngine(enable_fuzzy=False)
        jobs = [
            make_job(url="http://a.com"),
            make_job(url="http://a.com"),  # url dup
            make_job(url="", title="Dev", company="X", location="Y"),
            make_job(url="", title="Dev", company="X", location="Y"),  # fingerprint dup
        ]
        unique, result = engine.deduplicate(jobs)
        assert result.total_input == 4
        assert result.unique_count == 2
        assert result.duplicate_count == 2

    def test_dedup_empty_list(self):
        engine = DedupEngine(enable_fuzzy=False)
        unique, result = engine.deduplicate([])
        assert unique == []
        assert result.total_input == 0

    def test_dedup_all_unique(self):
        engine = DedupEngine(enable_fuzzy=False)
        # Use distinct title+company+location so fingerprint doesn't collide
        jobs = [
            make_job(title="Job A", company="Corp1", location="Tel Aviv", url="http://a.com"),
            make_job(title="Job B", company="Corp2", location="Haifa", url="http://b.com"),
            make_job(title="Job C", company="Corp3", location="Jerusalem", url="http://c.com"),
        ]
        unique, result = engine.deduplicate(jobs)
        assert len(unique) == 3
        assert result.duplicate_count == 0

    def test_reset_clears_state(self):
        engine = DedupEngine(enable_fuzzy=False)
        job = make_job(url="http://x.com")
        engine.add(job)
        is_dup, _ = engine.is_duplicate(job)
        assert is_dup is True

        engine.reset()
        is_dup, _ = engine.is_duplicate(job)
        assert is_dup is False

    def test_first_occurrence_wins(self):
        engine = DedupEngine(enable_fuzzy=False)
        jobs = [
            make_job(title="Original", url="http://x.com"),
            make_job(title="Copy", url="http://x.com"),
        ]
        unique, _ = engine.deduplicate(jobs)
        assert len(unique) == 1
        assert unique[0].title == "Original"


# ── DedupEngine: fuzzy disabled gracefully ────────────────────────────────────

class TestDedupEngineFuzzyDisabled:
    def test_fuzzy_disabled_still_deduplicates_by_url(self):
        engine = DedupEngine(enable_fuzzy=False)
        jobs = [make_job(url="http://x.com"), make_job(url="http://x.com")]
        unique, result = engine.deduplicate(jobs)
        assert len(unique) == 1


# ── DedupResult dataclass ─────────────────────────────────────────────────────

class TestDedupResult:
    def test_default_values(self):
        r = DedupResult()
        assert r.total_input == 0
        assert r.duplicate_count == 0
        assert r.unique_count == 0
