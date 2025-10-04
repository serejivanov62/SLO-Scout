"""
API dependencies for FastAPI dependency injection
"""
from typing import Generator
from sqlalchemy.orm import Session
from ..storage.timescale_manager import get_timescale_manager


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for database sessions

    Yields:
        SQLAlchemy Session instance
    """
    db_manager = get_timescale_manager()
    # get_session() returns a context manager, so we need to enter it
    with db_manager.get_session() as session:
        yield session
