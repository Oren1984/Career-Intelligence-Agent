# llm/providers/claude_provider.py
# Part of the Career Intelligence Agent project.
"""Claude (Anthropic) LLM provider."""
import os
import logging
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_API_KEY_ENV = "ANTHROPIC_API_KEY"
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


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


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider. Requires ANTHROPIC_API_KEY environment variable."""

    provider_name = "claude"

    def __init__(self, model: str | None = None):
        self.api_key = os.environ.get(_API_KEY_ENV)
        self.model = model or os.environ.get("CLAUDE_MODEL", _DEFAULT_MODEL)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic package not installed. Run: pip install anthropic"
                ) from exc
        return self._client

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze_job(self, job_title: str, job_description: str, profile_summary: str) -> str:
        try:
            client = self._get_client()
            prompt = _build_prompt(job_title, job_description, profile_summary)
            message = client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return f"[Claude Analysis]\n{message.content[0].text}"
        except Exception as exc:
            logger.error("Claude provider failed: %s", exc)
            return f"[Claude Analysis Failed: {exc}]"
