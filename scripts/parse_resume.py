# scripts/parse_resume.py
# Part of the Career Intelligence Agent project.
"""
Resume parser — extract candidate information from a PDF resume and
update the candidate profile files automatically.

Usage:
    python scripts/parse_resume.py resume.pdf
    python scripts/parse_resume.py resume.pdf --output-dir data/candidate_profile
    python scripts/parse_resume.py resume.pdf --dry-run

Process:
    1. Extract raw text from the PDF (pypdf preferred, pdfminer.six as fallback)
    2. If an LLM provider is configured, use it to extract structured data
    3. Otherwise, fall back to keyword-based extraction
    4. Write results to:
         data/candidate_profile/summary.txt
         data/candidate_profile/skills.json

Dependencies (optional — install at least one PDF library):
    pip install pypdf>=4.0.0
    pip install pdfminer.six>=20221105
"""
import sys
import os
import json
import argparse
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("parse_resume")

_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "candidate_profile"

# Common tech keywords for fallback extraction
_TECH_KEYWORDS: dict[str, list[str]] = {
    "ai_ml": [
        "machine learning", "deep learning", "llm", "rag", "nlp", "computer vision",
        "neural network", "pytorch", "tensorflow", "scikit-learn", "sklearn",
        "transformers", "hugging face", "langchain", "openai", "anthropic",
        "prompt engineering", "fine-tuning", "embeddings", "vector database",
        "mlops", "generative ai",
    ],
    "python": [
        "python", "fastapi", "django", "flask", "asyncio", "pydantic",
        "sqlalchemy", "pytest", "numpy", "pandas", "jupyter",
    ],
    "cloud_infra": [
        "aws", "gcp", "google cloud", "azure", "terraform", "docker",
        "kubernetes", "k8s", "ci/cd", "github actions", "jenkins", "airflow",
        "sagemaker", "vertex ai", "devops",
    ],
    "data": [
        "sql", "postgresql", "mysql", "mongodb", "redis", "spark",
        "kafka", "dbt", "bigquery", "snowflake", "data pipeline", "etl",
    ],
    "tools": [
        "git", "github", "linux", "bash", "rest api", "graphql",
        "microservices", "agile", "scrum",
    ],
}


# ── PDF text extraction ────────────────────────────────────────────────────────

def extract_text_pypdf(path: Path) -> str:
    """Extract text using pypdf."""
    import pypdf
    reader = pypdf.PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def extract_text_pdfminer(path: Path) -> str:
    """Extract text using pdfminer.six."""
    from pdfminer.high_level import extract_text
    return extract_text(str(path))


def extract_pdf_text(path: Path) -> str:
    """Try pypdf then pdfminer.six. Raise if neither is available or file is missing."""
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")
    errors = []

    try:
        text = extract_text_pypdf(path)
        if text.strip():
            logger.info("Text extracted with pypdf (%d chars)", len(text))
            return text
    except ImportError:
        errors.append("pypdf not installed")
    except Exception as exc:
        errors.append(f"pypdf error: {exc}")

    try:
        text = extract_text_pdfminer(path)
        if text.strip():
            logger.info("Text extracted with pdfminer.six (%d chars)", len(text))
            return text
    except ImportError:
        errors.append("pdfminer.six not installed")
    except Exception as exc:
        errors.append(f"pdfminer error: {exc}")

    raise RuntimeError(
        "Could not extract PDF text. Install a PDF library:\n"
        "  pip install pypdf>=4.0.0\n"
        "  pip install pdfminer.six>=20221105\n"
        f"Errors: {'; '.join(errors)}"
    )


# ── Keyword-based fallback extraction ─────────────────────────────────────────

def extract_keywords_fallback(text: str) -> dict:
    """
    Extract skills by searching for known tech keywords in the resume text.
    Returns a dict suitable for skills.json.
    """
    text_lower = text.lower()
    found: dict[str, list[str]] = {}

    for category, keywords in _TECH_KEYWORDS.items():
        hits = []
        for kw in keywords:
            if kw in text_lower:
                # Title-case for readability, preserve acronyms
                display = kw.upper() if len(kw) <= 4 and kw.isupper() or kw in (
                    "aws", "gcp", "sql", "llm", "rag", "nlp", "etl", "dbt", "k8s",
                ) else kw.title()
                hits.append(display)
        if hits:
            found[category] = hits

    return found


def build_summary_fallback(text: str, max_chars: int = 500) -> str:
    """
    Build a rough summary from the first meaningful paragraph of the resume.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    # Skip very short lines (headers, single words)
    paragraphs = [line for line in lines if len(line) > 40]
    if not paragraphs:
        return ""
    return " ".join(paragraphs[:3])[:max_chars]


# ── LLM-assisted extraction ────────────────────────────────────────────────────

_LLM_PROMPT = (
    "You are a career data extractor. Given the resume text below, "
    "return a JSON object with exactly these fields:\n"
    "\n"
    "{{\n"
    '  "summary": "<2-3 sentence professional summary>",\n'
    '  "skills": {{\n'
    '    "ai_ml": ["<skill>", ...],\n'
    '    "python": ["<skill>", ...],\n'
    '    "cloud_infra": ["<skill>", ...],\n'
    '    "data": ["<skill>", ...],\n'
    '    "tools": ["<skill>", ...]\n'
    "  }},\n"
    '  "keywords": ["<key technical term>", ...]\n'
    "}}\n"
    "\n"
    "Only include skills actually mentioned in the resume.\n"
    "Return valid JSON only — no explanation, no markdown.\n"
    "\n"
    "RESUME TEXT:\n"
    "{text}"
)


def extract_with_llm(text: str) -> dict | None:
    """Use the configured LLM provider to extract structured resume data."""
    try:
        from app.llm.provider_factory import get_provider
        provider = get_provider()

        if provider.provider_name == "mock":
            logger.info("LLM provider is mock — skipping LLM extraction")
            return None

        prompt = _LLM_PROMPT.format(text=text[:4000])
        logger.info("Extracting resume data with %s provider...", provider.provider_name)

        raw = provider.analyze_job(
            job_title="Resume Extraction",
            job_description=text[:4000],
            profile_summary=prompt,
        )

        # Strip provider prefix tags like "[Claude Analysis]\n..."
        if "\n" in raw:
            raw = raw.split("\n", 1)[1] if raw.startswith("[") else raw

        # Find JSON block
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            logger.warning("LLM did not return a JSON object")
            return None

        data = json.loads(raw[start:end])
        logger.info("LLM extraction successful")
        return data

    except Exception as exc:
        logger.warning("LLM extraction failed: %s — using fallback", exc)
        return None


# ── File writing ───────────────────────────────────────────────────────────────

def write_profile_files(
    summary: str,
    skills: dict,
    output_dir: Path,
    dry_run: bool = False,
) -> None:
    """Write summary.txt and skills.json to the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "summary.txt"
    skills_path = output_dir / "skills.json"

    if dry_run:
        print("\n=== DRY RUN — files NOT written ===")
        print(f"\n[{summary_path}]\n{summary}")
        print(f"\n[{skills_path}]\n{json.dumps(skills, indent=2)}")
        return

    summary_path.write_text(summary, encoding="utf-8")
    logger.info("Written: %s", summary_path)

    with open(skills_path, "w", encoding="utf-8") as f:
        json.dump(skills, f, indent=2)
    logger.info("Written: %s", skills_path)


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_resume(
    pdf_path: Path,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
    dry_run: bool = False,
) -> dict:
    """
    Full pipeline: extract PDF text → structure data → write profile files.

    Returns a dict with 'summary' and 'skills' keys.
    """
    logger.info("Parsing resume: %s", pdf_path)

    # Step 1: Extract text (extract_pdf_text raises FileNotFoundError if missing)
    text = extract_pdf_text(pdf_path)
    if not text.strip():
        raise ValueError("No text extracted from PDF. Is it a scanned image PDF?")

    logger.info("Extracted %d characters of text", len(text))

    # Step 2: Try LLM extraction, fall back to keyword extraction
    llm_data = extract_with_llm(text)

    if llm_data and "skills" in llm_data:
        summary = llm_data.get("summary", "") or build_summary_fallback(text)
        skills = llm_data.get("skills", {})
        # Merge any LLM keywords into skills["keywords"] category
        if llm_data.get("keywords"):
            skills.setdefault("keywords", llm_data["keywords"])
        logger.info("Using LLM-extracted data")
    else:
        summary = build_summary_fallback(text)
        skills = extract_keywords_fallback(text)
        logger.info("Using keyword-based fallback extraction")

    # Step 3: Write files
    write_profile_files(summary, skills, output_dir, dry_run=dry_run)

    return {"summary": summary, "skills": skills}


def main():
    parser = argparse.ArgumentParser(
        description="Parse a PDF resume and update the candidate profile.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/parse_resume.py resume.pdf
  python scripts/parse_resume.py resume.pdf --dry-run
  python scripts/parse_resume.py resume.pdf --output-dir data/candidate_profile

Requirements (install at least one):
  pip install pypdf>=4.0.0
  pip install pdfminer.six>=20221105
        """,
    )
    parser.add_argument("resume", type=Path, help="Path to the PDF resume file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory for profile files (default: {_DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview extracted data without writing files",
    )
    args = parser.parse_args()

    try:
        result = parse_resume(args.resume, output_dir=args.output_dir, dry_run=args.dry_run)
        if not args.dry_run:
            print("\nResume parsed successfully.")
            print(f"Summary: {result['summary'][:100]}...")
            skill_count = sum(len(v) for v in result["skills"].values())
            print(f"Skills extracted: {skill_count} across {len(result['skills'])} categories")
            print(f"Files written to: {args.output_dir}")
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
