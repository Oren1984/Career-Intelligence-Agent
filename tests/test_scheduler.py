# tests/test_scheduler.py
# Part of the Career Intelligence Agent project.
"""Tests for V2 scheduling module."""
import pytest
from unittest.mock import MagicMock, patch


class TestSchedulerModule:
    def test_is_available_returns_bool(self):
        from app.scheduler.scheduler import is_available
        result = is_available()
        assert isinstance(result, bool)

    def test_run_once_calls_collect_and_score(self):
        from app.scheduler.scheduler import run_once

        collect_fn = MagicMock()
        score_fn = MagicMock()

        run_once(collect_fn, score_fn)

        collect_fn.assert_called_once()
        score_fn.assert_called_once()

    def test_run_once_returns_dict(self):
        from app.scheduler.scheduler import run_once

        results = run_once(lambda: None, lambda: None)
        assert isinstance(results, dict)
        assert "collect" in results
        assert "score" in results

    def test_run_once_success_values(self):
        from app.scheduler.scheduler import run_once

        results = run_once(lambda: None, lambda: None)
        assert results["collect"] == "ok"
        assert results["score"] == "ok"

    def test_run_once_handles_collect_error(self):
        from app.scheduler.scheduler import run_once

        def failing_collect():
            raise RuntimeError("network error")

        results = run_once(failing_collect, lambda: None)
        assert results["collect"].startswith("error:")
        assert results["score"] == "ok"  # score still runs

    def test_run_once_handles_score_error(self):
        from app.scheduler.scheduler import run_once

        def failing_score():
            raise RuntimeError("db error")

        results = run_once(lambda: None, failing_score)
        assert results["collect"] == "ok"
        assert results["score"].startswith("error:")

    def test_run_once_both_fail(self):
        from app.scheduler.scheduler import run_once

        results = run_once(
            lambda: (_ for _ in ()).throw(RuntimeError("c")),
            lambda: (_ for _ in ()).throw(RuntimeError("s")),
        )
        assert results["collect"].startswith("error:")
        assert results["score"].startswith("error:")

    def test_create_scheduler_raises_if_no_apscheduler(self):
        from app.scheduler.scheduler import create_scheduler
        with patch("app.scheduler.scheduler._apscheduler_available", return_value=False):
            with pytest.raises(ImportError, match="APScheduler"):
                create_scheduler(lambda: None, lambda: None)

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("apscheduler"),
        reason="APScheduler not installed",
    )
    def test_create_scheduler_returns_scheduler(self):
        from app.scheduler.scheduler import create_scheduler, safe_shutdown
        scheduler = create_scheduler(lambda: None, lambda: None)
        assert scheduler is not None
        # Verify jobs are registered
        jobs = scheduler.get_jobs()
        job_ids = {j.id for j in jobs}
        assert "collect_jobs" in job_ids
        assert "score_jobs" in job_ids
        safe_shutdown(scheduler, wait=False)

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("apscheduler"),
        reason="APScheduler not installed",
    )
    def test_create_scheduler_custom_cron(self):
        from app.scheduler.scheduler import create_scheduler, safe_shutdown
        scheduler = create_scheduler(
            lambda: None,
            lambda: None,
            collect_cron="0 12 * * *",
            score_cron="30 12 * * *",
        )
        assert scheduler is not None
        safe_shutdown(scheduler, wait=False)
