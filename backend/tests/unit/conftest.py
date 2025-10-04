"""
Shared fixtures for unit tests

Provides database session mocking and common test data
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from src.models.base import Base


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """
    Create an in-memory SQLite database for testing

    Each test gets a fresh database session that is rolled back after the test
    """
    # Create in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False}
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session factory
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create session
    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
