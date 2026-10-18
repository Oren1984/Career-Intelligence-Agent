# tests/conftest.py
# Part of the Career Intelligence Agent project.
"""Shared pytest fixtures."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session for each test function."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def sample_profile():
    return {
        "target_roles": ["Applied AI Engineer", "MLOps Engineer", "AI Engineer"],
        "positive_keywords": ["python", "ai", "ml", "docker", "fastapi", "terraform", "aws", "llm", "rag"],
        "negative_keywords": ["phd", "senior", "principal", "relocation"],
    }
