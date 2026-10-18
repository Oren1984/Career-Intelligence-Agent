# collectors/mock_collector.py
# this file defines the MockCollector class to
# generate realistic demo job data for testing and demos

"""Mock collector that generates realistic demo job data for testing and demos."""
import logging
from datetime import datetime, timedelta, timezone
from app.collectors.base import BaseCollector, RawJob

logger = logging.getLogger(__name__)

_MOCK_JOBS = [
    {
        "title": "AI Engineer",
        "company": "TechCorp AI",
        "location": "Remote",
        "description": (
            "We are looking for an AI Engineer to help build and deploy ML models. "
            "You will work with Python, FastAPI, Docker, and AWS. "
            "Experience with LLM, RAG pipelines, and MLOps is a big plus. "
            "You will design scalable AI services and integrate them into production systems."
        ),
        "url": "https://example.com/jobs/1",
        "days_ago": 1,
    },
    {
        "title": "MLOps Engineer",
        "company": "DataFlow Inc",
        "location": "New York, NY",
        "description": (
            "MLOps Engineer needed to manage model pipelines, Docker containers, and Terraform infra on AWS. "
            "Must have strong Python skills and experience with CI/CD for ML. "
            "Familiarity with Kubernetes and monitoring tools is a plus."
        ),
        "url": "https://example.com/jobs/2",
        "days_ago": 2,
    },
    {
        "title": "Senior Machine Learning Engineer",
        "company": "BigData Corp",
        "location": "San Francisco, CA",
        "description": (
            "Senior ML Engineer with 8+ years experience in deep learning, Python, and distributed training. "
            "Must have PhD or equivalent research background. "
            "Will lead a team building next-gen AI products."
        ),
        "url": "https://example.com/jobs/3",
        "days_ago": 3,
    },
    {
        "title": "Applied AI Engineer",
        "company": "StartupAI",
        "location": "Remote",
        "description": (
            "Join our small team to build LLM-powered applications using Python and FastAPI. "
            "We use Docker, AWS, and Terraform for infrastructure. "
            "Experience with RAG, embeddings, and AI agent frameworks is highly valued."
        ),
        "url": "https://example.com/jobs/4",
        "days_ago": 1,
    },
    {
        "title": "Backend Python Developer",
        "company": "WebSoft",
        "location": "Austin, TX",
        "description": (
            "Backend developer with Python and FastAPI experience. "
            "You will build REST APIs and integrate third-party services. "
            "Docker knowledge is required. AWS is a plus."
        ),
        "url": "https://example.com/jobs/5",
        "days_ago": 4,
    },
    {
        "title": "Data Scientist",
        "company": "Analytics Pro",
        "location": "Remote",
        "description": (
            "Data Scientist with ML and Python skills to analyze large datasets. "
            "Experience with scikit-learn, pandas, and SQL required. "
            "AI and LLM experience is a bonus."
        ),
        "url": "https://example.com/jobs/6",
        "days_ago": 2,
    },
    {
        "title": "Principal AI Research Scientist",
        "company": "ResearchLab",
        "location": "Boston, MA",
        "description": (
            "Principal Scientist to lead AI research programs. "
            "PhD required. 10+ years of experience in ML, NLP, and AI. "
            "Must be willing to relocate to Boston."
        ),
        "url": "https://example.com/jobs/7",
        "days_ago": 5,
    },
    {
        "title": "LLM Platform Engineer",
        "company": "CloudAI",
        "location": "Remote",
        "description": (
            "Build and maintain LLM infrastructure using Python, Docker, AWS, and Terraform. "
            "You will design APIs with FastAPI, integrate RAG systems, and deploy ML models at scale. "
            "Strong experience with MLOps workflows required."
        ),
        "url": "https://example.com/jobs/8",
        "days_ago": 1,
    },
    {
        "title": "DevOps Engineer",
        "company": "InfraOps",
        "location": "Remote",
        "description": (
            "DevOps Engineer with Terraform, AWS, and Docker expertise. "
            "CI/CD pipeline design and Kubernetes management. "
            "Python scripting is required."
        ),
        "url": "https://example.com/jobs/9",
        "days_ago": 3,
    },
    {
        "title": "Full Stack Developer",
        "company": "WebDev Co",
        "location": "Chicago, IL",
        "description": (
            "Full stack developer with React and Node.js skills. "
            "Python experience is a plus. No AI or ML required."
        ),
        "url": "https://example.com/jobs/10",
        "days_ago": 7,
    },
    {
        "title": "Machine Learning Engineer",
        "company": "AutoML Labs",
        "location": "Remote",
        "description": (
            "ML Engineer to develop and productionize models using Python, Docker, and AWS. "
            "Experience with MLOps, model monitoring, and AI pipelines. "
            "LLM fine-tuning experience is highly valued."
        ),
        "url": "https://example.com/jobs/11",
        "days_ago": 2,
    },
    {
        "title": "AI Product Manager",
        "company": "ProductAI",
        "location": "Remote",
        "description": (
            "Product Manager for AI products. "
            "Work closely with ML and AI teams to define roadmap. "
            "No coding required, but understanding of Python and LLM products is beneficial."
        ),
        "url": "https://example.com/jobs/12",
        "days_ago": 6,
    },
    {
        "title": "Cloud AI Architect",
        "company": "EnterpriseCloud",
        "location": "Remote — must relocate to Seattle",
        "description": (
            "Senior Cloud Architect with AI specialization. "
            "Design AI solutions on AWS with Terraform and Docker. "
            "Python and MLOps background required. Relocation package available."
        ),
        "url": "https://example.com/jobs/13",
        "days_ago": 4,
    },
    {
        "title": "Conversational AI Engineer",
        "company": "ChatBot Inc",
        "location": "Remote",
        "description": (
            "Build conversational AI systems using LLMs, Python, and FastAPI. "
            "Experience with RAG architectures, vector databases, and Docker. "
            "AWS deployment experience preferred."
        ),
        "url": "https://example.com/jobs/14",
        "days_ago": 1,
    },
    {
        "title": "AI Infrastructure Engineer",
        "company": "ScaleAI Tech",
        "location": "Remote",
        "description": (
            "Infrastructure Engineer focused on AI/ML workloads. "
            "Terraform, AWS, Docker, and Kubernetes expertise required. "
            "Python automation scripting. Collaborate with ML teams to optimize training pipelines."
        ),
        "url": "https://example.com/jobs/15",
        "days_ago": 2,
    },
]


class MockCollector(BaseCollector):
    """Returns hardcoded demo job data. Useful for testing and demos without network access."""

    source_name = "mock"

    def collect(self) -> list[RawJob]:
        jobs = []
        for item in _MOCK_JOBS:
            date_found = datetime.now(timezone.utc) - timedelta(days=item.get("days_ago", 0))
            raw = RawJob(
                title=item["title"],
                company=item["company"],
                location=item["location"],
                description=item["description"],
                url=item["url"],
                source=self.source_name,
                raw_text=item["description"],
                date_found=date_found,
            )
            jobs.append(raw)
        logger.info("MockCollector collected %d jobs", len(jobs))
        return jobs
