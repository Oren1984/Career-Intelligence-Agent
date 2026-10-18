# llm/providers/openai_provider.py
# Part of the Career Intelligence Agent project.
"""OpenAI LLM provider."""
import os
import logging
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_API_KEY_ENV = "OPENAI_API_KEY"
_DEFAULT_MODEL = "gpt-4o-mini"


def _build_prompt(job_title: str, job_description: str, profile_summary: str) -> str:
    return (
        f"You are a career advisor. Analyze this job posting for the candidate.\n\n"
        f"CANDIDATE PROFILE:\n{profile_summary}\n\n"
        f"JOB TITLE: {job_title}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:2000]}\n\n"
        f"Provide a concise analysis (3-5 sentences) covering:\n"
        f"1. How well this job matches the candidate's profile\n"
        f"2. Key strengths or alignment points\n"
        f"3. Any concerns or mismatches\n"
        f"4. A brief recommendation (apply / review further / skip)\n\n"
        f"Be direct and practical."
    )


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider. Requires OPENAI_API_KEY environment variable."""

    provider_name = "openai"

    def __init__(self, model: str | None = None):
        self.api_key = os.environ.get(_API_KEY_ENV)
        self.model = model or os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(api_key=self.api_key)
            except ImportError as exc:
                raise RuntimeError(
                    "openai package not installed. Run: pip install openai"
                ) from exc
        return self._client

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze_job(self, job_title: str, job_description: str, profile_summary: str) -> str:
        try:
            client = self._get_client()
            prompt = _build_prompt(job_title, job_description, profile_summary)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
            )
            return f"[OpenAI Analysis]\n{response.choices[0].message.content}"
        except Exception as exc:
            logger.error("OpenAI provider failed: %s", exc)
            return f"[OpenAI Analysis Failed: {exc}]"
