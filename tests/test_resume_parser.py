# tests/test_resume_parser.py
# Part of the Career Intelligence Agent project.
"""Tests for V3 resume parser — text extraction, keyword fallback, LLM extraction, file writing."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── Text extraction ────────────────────────────────────────────────────────────

class TestPdfTextExtraction:
    def test_extract_pdf_text_raises_if_no_library(self, tmp_path):
        from scripts.parse_resume import extract_pdf_text

        fake_pdf = tmp_path / "test.pdf"
        fake_pdf.write_bytes(b"fake pdf content")

        with patch("scripts.parse_resume.extract_text_pypdf", side_effect=ImportError("no pypdf")):
            with patch("scripts.parse_resume.extract_text_pdfminer", side_effect=ImportError("no pdfminer")):
                with pytest.raises(RuntimeError, match="Could not extract PDF text"):
                    extract_pdf_text(fake_pdf)

    def test_extract_pdf_text_falls_back_to_pdfminer(self, tmp_path):
        """If pypdf returns empty text, should fall back to pdfminer."""
        from scripts.parse_resume import extract_pdf_text

        fake_pdf = tmp_path / "test.pdf"
        fake_pdf.write_bytes(b"fake pdf content")

        with patch("scripts.parse_resume.extract_text_pypdf", return_value=""):
            with patch("scripts.parse_resume.extract_text_pdfminer", return_value="Extracted text"):
                result = extract_pdf_text(fake_pdf)

        assert result == "Extracted text"

    def test_extract_pdf_text_uses_pypdf_first(self, tmp_path):
        fake_pdf = tmp_path / "test.pdf"
        fake_pdf.write_bytes(b"fake pdf content")

        from scripts.parse_resume import extract_pdf_text

        with patch("scripts.parse_resume.extract_text_pypdf", return_value="PyPDF text") as mock_pypdf:
            result = extract_pdf_text(fake_pdf)

        mock_pypdf.assert_called_once()
        assert result == "PyPDF text"


# ── Keyword extraction fallback ────────────────────────────────────────────────

class TestKeywordFallback:
    def test_returns_dict(self):
        from scripts.parse_resume import extract_keywords_fallback
        result = extract_keywords_fallback("I know python and docker")
        assert isinstance(result, dict)

    def test_finds_python(self):
        from scripts.parse_resume import extract_keywords_fallback
        result = extract_keywords_fallback("Expert in Python and FastAPI development")
        assert "python" in result
        python_skills = result["python"]
        assert any("python" in s.lower() for s in python_skills)

    def test_finds_ml_skills(self):
        from scripts.parse_resume import extract_keywords_fallback
        result = extract_keywords_fallback("Experienced with machine learning and LLM fine-tuning")
        assert "ai_ml" in result

    def test_finds_cloud_skills(self):
        from scripts.parse_resume import extract_keywords_fallback
        result = extract_keywords_fallback("Deployed on AWS using Terraform and Docker")
        assert "cloud_infra" in result

    def test_empty_text_returns_empty(self):
        from scripts.parse_resume import extract_keywords_fallback
        result = extract_keywords_fallback("")
        assert result == {}

    def test_unrelated_text_returns_empty(self):
        from scripts.parse_resume import extract_keywords_fallback
        result = extract_keywords_fallback("I like cooking and baking bread.")
        assert result == {}

    def test_case_insensitive(self):
        from scripts.parse_resume import extract_keywords_fallback
        result = extract_keywords_fallback("PYTHON EXPERT with DOCKER experience")
        assert "python" in result or "cloud_infra" in result


# ── Summary extraction fallback ───────────────────────────────────────────────

class TestSummaryFallback:
    def test_returns_string(self):
        from scripts.parse_resume import build_summary_fallback
        text = "John Doe\nSenior Software Engineer with 5 years of experience in AI and ML systems."
        result = build_summary_fallback(text)
        assert isinstance(result, str)

    def test_max_chars_respected(self):
        from scripts.parse_resume import build_summary_fallback
        long_text = "A " * 1000
        result = build_summary_fallback(long_text, max_chars=100)
        assert len(result) <= 100

    def test_skips_short_lines(self):
        from scripts.parse_resume import build_summary_fallback
        text = "Name\nJohn Doe\nExperienced software engineer specializing in machine learning and AI systems."
        result = build_summary_fallback(text)
        # Should include the long line, skip short ones
        assert len(result) > 0


# ── LLM extraction ─────────────────────────────────────────────────────────────

class TestLLMExtraction:
    def test_returns_none_for_mock_provider(self):
        from scripts.parse_resume import extract_with_llm
        from app.llm.mock_provider import MockLLMProvider

        with patch("app.llm.provider_factory.get_provider", return_value=MockLLMProvider()):
            result = extract_with_llm("Resume text here")

        assert result is None

    def test_returns_none_on_invalid_json(self):
        from scripts.parse_resume import extract_with_llm

        mock_provider = MagicMock()
        mock_provider.provider_name = "test"
        mock_provider.analyze_job.return_value = "not valid json at all!!!"

        with patch("app.llm.provider_factory.get_provider", return_value=mock_provider):
            result = extract_with_llm("Resume text here")

        assert result is None

    def test_parses_valid_llm_json(self):
        from scripts.parse_resume import extract_with_llm

        llm_output = json.dumps({
            "summary": "Experienced AI engineer",
            "skills": {"python": ["Python", "FastAPI"]},
            "keywords": ["LLM", "RAG"],
        })

        mock_provider = MagicMock()
        mock_provider.provider_name = "test"
        mock_provider.analyze_job.return_value = llm_output

        with patch("app.llm.provider_factory.get_provider", return_value=mock_provider):
            result = extract_with_llm("Resume text here")

        assert result is not None
        assert result["summary"] == "Experienced AI engineer"
        assert "python" in result["skills"]

    def test_handles_provider_exception_gracefully(self):
        from scripts.parse_resume import extract_with_llm

        mock_provider = MagicMock()
        mock_provider.provider_name = "test"
        mock_provider.analyze_job.side_effect = RuntimeError("API down")

        with patch("app.llm.provider_factory.get_provider", return_value=mock_provider):
            result = extract_with_llm("Resume text here")

        assert result is None


# ── File writing ───────────────────────────────────────────────────────────────

class TestWriteProfileFiles:
    def test_writes_summary_txt(self, tmp_path):
        from scripts.parse_resume import write_profile_files
        write_profile_files("My summary", {"python": ["Python"]}, tmp_path)
        assert (tmp_path / "summary.txt").read_text() == "My summary"

    def test_writes_skills_json(self, tmp_path):
        from scripts.parse_resume import write_profile_files
        skills = {"python": ["Python", "FastAPI"], "cloud": ["AWS"]}
        write_profile_files("Summary", skills, tmp_path)
        loaded = json.loads((tmp_path / "skills.json").read_text())
        assert loaded == skills

    def test_creates_output_dir(self, tmp_path):
        from scripts.parse_resume import write_profile_files
        new_dir = tmp_path / "new" / "subdir"
        write_profile_files("Summary", {}, new_dir)
        assert (new_dir / "summary.txt").exists()

    def test_dry_run_does_not_write(self, tmp_path):
        from scripts.parse_resume import write_profile_files
        write_profile_files("Summary", {"x": ["Y"]}, tmp_path, dry_run=True)
        assert not (tmp_path / "summary.txt").exists()
        assert not (tmp_path / "skills.json").exists()


# ── Full pipeline ──────────────────────────────────────────────────────────────

class TestParseResumePipeline:
    def test_full_pipeline_with_mock(self, tmp_path):
        from scripts.parse_resume import parse_resume
        from app.llm.mock_provider import MockLLMProvider

        resume_text = (
            "Jane Doe — AI Engineer\n\n"
            "Senior engineer with 5+ years building ML systems using Python and Docker.\n"
            "Experience with AWS, Terraform, LLM fine-tuning, and RAG pipelines.\n"
            "Built FastAPI services deployed on Kubernetes."
        )

        with patch("scripts.parse_resume.extract_pdf_text", return_value=resume_text):
            with patch("app.llm.provider_factory.get_provider", return_value=MockLLMProvider()):
                result = parse_resume(
                    Path("fake.pdf"),
                    output_dir=tmp_path,
                    dry_run=False,
                )

        assert "summary" in result
        assert "skills" in result
        assert (tmp_path / "summary.txt").exists()
        assert (tmp_path / "skills.json").exists()

    def test_pipeline_dry_run_no_files(self, tmp_path):
        from scripts.parse_resume import parse_resume
        from app.llm.mock_provider import MockLLMProvider

        resume_text = "Python developer with Docker and AWS experience working on ML systems."

        with patch("scripts.parse_resume.extract_pdf_text", return_value=resume_text):
            with patch("app.llm.provider_factory.get_provider", return_value=MockLLMProvider()):
                parse_resume(Path("fake.pdf"), output_dir=tmp_path, dry_run=True)

        assert not (tmp_path / "summary.txt").exists()

    def test_pipeline_raises_for_missing_file(self, tmp_path):
        from scripts.parse_resume import parse_resume
        with pytest.raises(FileNotFoundError):
            parse_resume(tmp_path / "nonexistent.pdf", output_dir=tmp_path)

    def test_pipeline_raises_for_empty_text(self, tmp_path):
        from scripts.parse_resume import parse_resume
        fake_pdf = tmp_path / "empty.pdf"
        fake_pdf.write_bytes(b"")

        with patch("scripts.parse_resume.extract_pdf_text", return_value=""):
            with pytest.raises(ValueError, match="No text extracted"):
                parse_resume(fake_pdf, output_dir=tmp_path)
