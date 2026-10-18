# tests/test_source_loader.py
# Part of the Career Intelligence Agent project.
"""Tests for source configuration loading and collector instantiation."""
import os
import pytest
import tempfile
import yaml

from app.collectors.source_loader import load_sources_config, load_collectors
from app.collectors.mock_collector import MockCollector
from app.collectors.rss_collector import RSSCollector


_SAMPLE_CONFIG = {
    "sources": [
        {
            "name": "mock",
            "enabled": True,
            "source_type": "mock",
            "notes": "Demo data",
            "priority": 0,
        },
        {
            "name": "test_rss",
            "enabled": True,
            "source_type": "rss",
            "url": "https://example.com/rss",
            "notes": "Test RSS feed",
            "priority": 1,
        },
        {
            "name": "linkedin",
            "enabled": False,
            "source_type": "manual_reference",
            "notes": "Not scraped",
            "priority": 99,
        },
        {
            "name": "greenhouse",
            "enabled": False,
            "source_type": "future",
            "notes": "V2",
            "priority": 50,
        },
    ]
}


@pytest.fixture
def sources_yaml_path():
    """Write a sample sources.yaml to a temp file and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as fh:
        yaml.dump(_SAMPLE_CONFIG, fh)
        path = fh.name
    yield path
    os.unlink(path)


class TestLoadSourcesConfig:
    def test_loads_all_sources(self, sources_yaml_path):
        sources = load_sources_config(sources_yaml_path)
        assert len(sources) == 4

    def test_returns_empty_for_missing_file(self):
        sources = load_sources_config("/nonexistent/path/sources.yaml")
        assert sources == []

    def test_source_fields_present(self, sources_yaml_path):
        sources = load_sources_config(sources_yaml_path)
        mock_src = next(s for s in sources if s["name"] == "mock")
        assert mock_src["enabled"] is True
        assert mock_src["source_type"] == "mock"
        assert mock_src["priority"] == 0

    def test_disabled_source_present_in_raw_config(self, sources_yaml_path):
        """load_sources_config returns ALL sources; filtering happens in load_collectors."""
        sources = load_sources_config(sources_yaml_path)
        linkedin = next(s for s in sources if s["name"] == "linkedin")
        assert linkedin["enabled"] is False


class TestLoadCollectors:
    def test_returns_mock_and_rss(self, sources_yaml_path):
        collectors = load_collectors(path=sources_yaml_path)
        types = {type(c).__name__ for c in collectors}
        assert "MockCollector" in types
        assert "RSSCollector" in types

    def test_disabled_sources_excluded(self, sources_yaml_path):
        """manual_reference and future sources should produce no collectors."""
        collectors = load_collectors(path=sources_yaml_path)
        # Only mock + rss should be instantiated (2 enabled sources)
        assert len(collectors) == 2

    def test_no_mock_excludes_mock(self, sources_yaml_path):
        collectors = load_collectors(path=sources_yaml_path, include_mock=False)
        types = [type(c).__name__ for c in collectors]
        assert "MockCollector" not in types
        assert "RSSCollector" in types

    def test_type_filter_rss_only(self, sources_yaml_path):
        collectors = load_collectors(path=sources_yaml_path, types=["rss"])
        assert all(isinstance(c, RSSCollector) for c in collectors)
        assert len(collectors) == 1

    def test_type_filter_mock_only(self, sources_yaml_path):
        collectors = load_collectors(path=sources_yaml_path, types=["mock"])
        assert all(isinstance(c, MockCollector) for c in collectors)

    def test_rss_feeds_batched_into_one_collector(self, sources_yaml_path):
        """Multiple RSS sources should be batched into a single RSSCollector."""
        config_with_two_rss = {
            "sources": [
                {"name": "feed1", "enabled": True, "source_type": "rss",
                 "url": "https://example.com/rss1", "priority": 1},
                {"name": "feed2", "enabled": True, "source_type": "rss",
                 "url": "https://example.com/rss2", "priority": 2},
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as fh:
            yaml.dump(config_with_two_rss, fh)
            path = fh.name

        try:
            collectors = load_collectors(path=path, include_mock=False)
            assert len(collectors) == 1
            assert isinstance(collectors[0], RSSCollector)
            assert len(collectors[0].feeds) == 2
        finally:
            os.unlink(path)

    def test_fallback_to_mock_if_no_config(self):
        """If sources.yaml is missing, load_collectors should fall back to MockCollector."""
        collectors = load_collectors(path="/nonexistent/sources.yaml", include_mock=True)
        assert len(collectors) == 1
        assert isinstance(collectors[0], MockCollector)

    def test_fallback_empty_if_no_config_no_mock(self):
        collectors = load_collectors(path="/nonexistent/sources.yaml", include_mock=False)
        assert collectors == []
