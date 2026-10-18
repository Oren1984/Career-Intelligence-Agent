# llm/base.py
# Part of the Career Intelligence Agent project.
"""Abstract LLM provider interface — future-ready for V2 integration."""
from abc import ABC, abstractmethod


# Note: This is a placeholder for the V2 refactor.
# The current implementation in V1 is in llm/providers.py.
class BaseLLMProvider(ABC):
    """
    Interface for LLM providers.
    Implement this to add OpenAI, Claude, Gemini, or local models in V2.
    """

    provider_name: str = "base"

    # Define a more structured return type for analyze_job, e.g. a dataclass with specific fields.
    @abstractmethod
    def analyze_job(self, job_title: str, job_description: str, profile_summary: str) -> str:
        """
        Generate a natural-language analysis of a job posting.

        Args:
            job_title: The job title.
            job_description: Full job description text.
            profile_summary: A summary of the candidate's profile.

        Returns:
            A string containing the LLM's analysis.
        """
        ...

    # This method can be used to check if the provider is properly configured
    # and reachable before attempting to use it.
    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is properly configured and reachable."""
        ...
