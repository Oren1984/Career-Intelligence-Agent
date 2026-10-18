# llm/providers/gemini_provider.py
# Part of the Career Intelligence Agent project.
"""Google Gemini LLM provider."""
import os
import logging
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_API_KEY_ENV = "GOOGLE_API_KEY"
_DEFAULT_MODEL = "gemini-1.5-flash"


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


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider. Requires GOOGLE_API_KEY environment variable."""

    provider_name = "gemini"

    def __init__(self, model: str | None = None):
        self.api_key = os.environ.get(_API_KEY_ENV)
        self.model = model or os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import google.generativeai  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze_job(self, job_title: str, job_description: str, profile_summary: str) -> str:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            prompt = _build_prompt(job_title, job_description, profile_summary)
            response = model.generate_content(prompt)
            return f"[Gemini Analysis]\n{response.text}"
        except ImportError:
            return "[Gemini Analysis Failed: google-generativeai not installed. Run: pip install google-generativeai]"
        except Exception as exc:
            logger.error("Gemini provider failed: %s", exc)
            return f"[Gemini Analysis Failed: {exc}]"
