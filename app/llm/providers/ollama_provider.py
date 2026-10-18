# llm/providers/ollama_provider.py
# Part of the Career Intelligence Agent project.
"""Ollama local LLM provider (placeholder for self-hosted models)."""
import os
import logging
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"


class OllamaProvider(BaseLLMProvider):
    """
    Ollama local provider for self-hosted LLMs.
    Requires Ollama to be running locally (https://ollama.com).
    Set OLLAMA_BASE_URL and OLLAMA_MODEL env vars to configure.
    """

    provider_name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        self.model = model or os.environ.get("OLLAMA_MODEL", _DEFAULT_MODEL)

    def is_available(self) -> bool:
        """Check if Ollama is reachable at the configured URL."""
        try:
            import requests
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def analyze_job(self, job_title: str, job_description: str, profile_summary: str) -> str:
        try:
            import requests
            prompt = (
                f"You are a career advisor. Analyze this job posting for the candidate.\n\n"
                f"CANDIDATE PROFILE:\n{profile_summary}\n\n"
                f"JOB TITLE: {job_title}\n\n"
                f"JOB DESCRIPTION:\n{job_description[:2000]}\n\n"
                f"Provide a concise analysis (3-5 sentences) covering match quality, "
                f"strengths, concerns, and a brief recommendation."
            )
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 512},
            }
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return f"[Ollama/{self.model} Analysis]\n{data.get('response', '').strip()}"
        except Exception as exc:
            logger.error("Ollama provider failed: %s", exc)
            return f"[Ollama Analysis Failed: {exc}]"
