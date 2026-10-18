# tests/test_llm_providers.py
# Part of the Career Intelligence Agent project.
"""Tests for V2 LLM provider layer — loading, fallback, and mock behavior."""
import os
from unittest.mock import patch

from app.llm.mock_provider import MockLLMProvider
from app.llm.provider_factory import get_provider, list_providers, KNOWN_PROVIDERS


# ── MockLLMProvider ────────────────────────────────────────────────────────────

class TestMockLLMProvider:
    def test_is_always_available(self):
        p = MockLLMProvider()
        assert p.is_available() is True

    def test_provider_name(self):
        assert MockLLMProvider.provider_name == "mock"

    def test_analyze_returns_string(self):
        p = MockLLMProvider()
        result = p.analyze_job("AI Engineer", "Requires Python and LLM experience", "Python developer")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_analyze_contains_mock_label(self):
        p = MockLLMProvider()
        result = p.analyze_job("AI Engineer", "Python, AI, Docker", "profile")
        assert "[Mock LLM Analysis]" in result

    def test_python_highlight(self):
        p = MockLLMProvider()
        result = p.analyze_job("Dev", "requires python skills", "profile")
        assert "Python" in result

    def test_senior_concern(self):
        p = MockLLMProvider()
        result = p.analyze_job("Senior Engineer", "senior role", "profile")
        assert "Seniority" in result or "senior" in result.lower()

    def test_no_keywords_shows_no_matches(self):
        p = MockLLMProvider()
        result = p.analyze_job("Accountant", "counting beans since 1990", "profile")
        assert "No strong keyword matches" in result


# ── Provider factory ────────────────────────────────────────────────────────────

class TestProviderFactory:
    def test_default_returns_mock(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LLM_PROVIDER", None)
            p = get_provider()
        assert isinstance(p, MockLLMProvider)

    def test_explicit_mock(self):
        p = get_provider("mock")
        assert isinstance(p, MockLLMProvider)

    def test_unknown_provider_falls_back_to_mock(self):
        p = get_provider("nonexistent_provider_xyz")
        assert isinstance(p, MockLLMProvider)

    def test_claude_without_key_falls_back_to_mock(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            p = get_provider("claude")
        assert isinstance(p, MockLLMProvider)

    def test_openai_without_key_falls_back_to_mock(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            p = get_provider("openai")
        assert isinstance(p, MockLLMProvider)

    def test_gemini_without_key_falls_back_to_mock(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}, clear=False):
            p = get_provider("gemini")
        assert isinstance(p, MockLLMProvider)

    def test_env_var_selects_provider(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "mock"}, clear=False):
            p = get_provider()
        assert isinstance(p, MockLLMProvider)

    def test_list_providers_returns_dict(self):
        result = list_providers()
        assert isinstance(result, dict)
        assert "mock" in result
        assert result["mock"] is True  # mock is always available

    def test_list_providers_contains_all_known(self):
        result = list_providers()
        for name in KNOWN_PROVIDERS:
            assert name in result

    def test_provider_is_available_after_factory(self):
        p = get_provider("mock")
        assert p.is_available() is True


# ── Individual provider classes ────────────────────────────────────────────────

class TestClaudeProvider:
    def test_not_available_without_key(self):
        from app.llm.providers.claude_provider import ClaudeProvider
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            p = ClaudeProvider()
            assert p.is_available() is False

    def test_provider_name(self):
        from app.llm.providers.claude_provider import ClaudeProvider
        assert ClaudeProvider.provider_name == "claude"


class TestOpenAIProvider:
    def test_not_available_without_key(self):
        from app.llm.providers.openai_provider import OpenAIProvider
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            p = OpenAIProvider()
            assert p.is_available() is False

    def test_provider_name(self):
        from app.llm.providers.openai_provider import OpenAIProvider
        assert OpenAIProvider.provider_name == "openai"


class TestGeminiProvider:
    def test_not_available_without_key(self):
        from app.llm.providers.gemini_provider import GeminiProvider
        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}, clear=False):
            p = GeminiProvider()
            assert p.is_available() is False

    def test_provider_name(self):
        from app.llm.providers.gemini_provider import GeminiProvider
        assert GeminiProvider.provider_name == "gemini"


class TestOllamaProvider:
    def test_provider_name(self):
        from app.llm.providers.ollama_provider import OllamaProvider
        assert OllamaProvider.provider_name == "ollama"

    def test_not_available_when_server_down(self):
        from app.llm.providers.ollama_provider import OllamaProvider
        p = OllamaProvider(base_url="http://localhost:19999")  # unlikely to be running
        assert p.is_available() is False
