# llm/provider_factory.py
# Part of the Career Intelligence Agent project.
"""LLM provider factory — loads the configured provider with graceful fallback to mock."""
import os
import logging
from app.llm.base import BaseLLMProvider
from app.llm.mock_provider import MockLLMProvider

logger = logging.getLogger(__name__)

_PROVIDER_ENV = "LLM_PROVIDER"
_DEFAULT_PROVIDER = "mock"

# Registry of known provider names
KNOWN_PROVIDERS = {"mock", "claude", "openai", "gemini", "ollama"}


# Note: In V2, we can refactor this to use dynamic loading or a plugin system for providers,
def get_provider(provider_name: str | None = None) -> BaseLLMProvider:
    """
    Return the configured LLM provider.

    Provider selection order:
    1. Explicit provider_name argument
    2. LLM_PROVIDER environment variable
    3. Default: "mock"

    If the selected provider is not available (missing API key or package),
    falls back to MockLLMProvider automatically.

    Example env config:
        LLM_PROVIDER=claude
        ANTHROPIC_API_KEY=sk-ant-...
    """
    name = (provider_name or os.environ.get(_PROVIDER_ENV, _DEFAULT_PROVIDER)).lower().strip()

    if name not in KNOWN_PROVIDERS:
        logger.warning("Unknown provider '%s'. Falling back to mock.", name)
        return MockLLMProvider()

    provider = _load_provider(name)

    if not provider.is_available():
        logger.warning(
            "Provider '%s' is not available (missing API key or package). Falling back to mock.",
            name,
        )
        return MockLLMProvider()

    logger.info("LLM provider loaded: %s", provider.provider_name)
    return provider


# Internal helper to load the provider class. Catches import errors and returns mock on failure.
def _load_provider(name: str) -> BaseLLMProvider:
    """Instantiate the named provider. Returns MockLLMProvider on any import error."""
    try:
        if name == "claude":
            from app.llm.providers.claude_provider import ClaudeProvider
            return ClaudeProvider()
        elif name == "openai":
            from app.llm.providers.openai_provider import OpenAIProvider
            return OpenAIProvider()
        elif name == "gemini":
            from app.llm.providers.gemini_provider import GeminiProvider
            return GeminiProvider()
        elif name == "ollama":
            from app.llm.providers.ollama_provider import OllamaProvider
            return OllamaProvider()
        else:
            return MockLLMProvider()
    except Exception as exc:
        logger.error("Failed to load provider '%s': %s. Using mock.", name, exc)
        return MockLLMProvider()


# Utility function to check availability of all known providers. Useful for diagnostics.
def list_providers() -> dict[str, bool]:
    """Return availability status for all known providers."""
    result = {}
    for name in KNOWN_PROVIDERS:
        try:
            p = _load_provider(name)
            result[name] = p.is_available()
        except Exception:
            result[name] = False
    return result
