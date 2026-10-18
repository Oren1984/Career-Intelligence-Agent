# tests/test_dashboard.py
# Part of the Career Intelligence Agent project.
"""Sanity tests for dashboard module import and key function availability."""


class TestDashboardImport:
    def test_streamlit_importable(self):
        """Verify streamlit is installed and importable."""
        import streamlit
        assert streamlit is not None

    def test_dashboard_module_is_importable(self):
        """
        The dashboard is a Streamlit script, so we test that all the internal
        modules it depends on can be imported cleanly.
        """
        from app.db.session import init_db, get_session
        from app.services.job_service import VALID_STATUSES
        assert callable(init_db)
        assert callable(get_session)
        assert isinstance(VALID_STATUSES, set)

    def test_valid_statuses_set(self):
        from app.services.job_service import VALID_STATUSES
        expected = {"new", "reviewing", "saved", "ignored", "applied_manual"}
        assert VALID_STATUSES == expected

    def test_dashboard_file_exists(self):
        from pathlib import Path
        dash_path = Path(__file__).parent.parent / "dashboard" / "streamlit_app.py"
        assert dash_path.exists(), f"Dashboard file not found at {dash_path}"

    def test_service_get_summary_stats(self, db_session, sample_profile):
        from app.services.job_service import JobService
        service = JobService(db_session, profile=sample_profile)
        stats = service.get_summary_stats()
        assert isinstance(stats, dict)
        assert "total_jobs" in stats

    def test_service_get_jobs_with_scores_empty(self, db_session, sample_profile):
        from app.services.job_service import JobService
        service = JobService(db_session, profile=sample_profile)
        jobs = service.get_jobs_with_scores()
        assert isinstance(jobs, list)
        assert len(jobs) == 0
