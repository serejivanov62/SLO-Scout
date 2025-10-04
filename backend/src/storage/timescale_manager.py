"""
TimescaleDB connection manager per T040
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from typing import Generator
import os


class TimescaleManager:
    """TimescaleDB connection and session management"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "sloscout",
        user: str = "sloscout",
        password: str = "changeme",
        pool_size: int = 10,
        max_overflow: int = 20
    ):
        # Build connection URL
        self.database_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"

        # Create engine with connection pooling
        self.engine = create_engine(
            self.database_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # Verify connections before using
            echo=False  # Set to True for SQL logging
        )

        # Session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        # Register event listeners
        self._register_listeners()

    def _register_listeners(self):
        """Register SQLAlchemy event listeners"""

        @event.listens_for(self.engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            """Set timezone on new connections"""
            cursor = dbapi_conn.cursor()
            cursor.execute("SET TIME ZONE 'UTC'")
            cursor.close()

        @event.listens_for(self.engine, "checkin")
        def receive_checkin(dbapi_conn, connection_record):
            """Reset connection state on checkin"""
            cursor = dbapi_conn.cursor()
            cursor.execute("ROLLBACK")  # Ensure clean state
            cursor.close()

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions

        Usage:
            with manager.get_session() as session:
                service = session.query(Service).first()
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def create_tables(self):
        """Create all tables (for testing/initialization)"""
        from ..models.base import Base
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self):
        """Drop all tables (for testing only!)"""
        from ..models.base import Base
        Base.metadata.drop_all(bind=self.engine)

    def compress_capsules(self):
        """
        Trigger manual compression of capsule hypertable

        Per FR-030: Compress after 7 days
        """
        with self.get_session() as session:
            session.execute("""
                CALL run_job((SELECT job_id FROM timescaledb_information.jobs
                              WHERE proc_name = 'policy_compression'
                              AND hypertable_name = 'capsule'));
            """)

    def cleanup_old_data(self):
        """
        Trigger retention policy manually

        Per FR-030: Drop capsules after 90 days
        """
        with self.get_session() as session:
            session.execute("""
                CALL run_job((SELECT job_id FROM timescaledb_information.jobs
                              WHERE proc_name = 'policy_retention'
                              AND hypertable_name = 'capsule'));
            """)

    def get_stats(self):
        """Get database statistics"""
        with self.get_session() as session:
            result = session.execute("""
                SELECT
                    hypertable_name,
                    num_chunks,
                    approximate_row_count,
                    total_size
                FROM timescaledb_information.hypertables
                WHERE hypertable_name IN ('capsule', 'slo');
            """)
            return [dict(row) for row in result]

    def close(self):
        """Close all connections"""
        self.engine.dispose()


# Singleton instance
_manager: TimescaleManager = None


def get_timescale_manager() -> TimescaleManager:
    """Get singleton TimescaleDB manager"""
    global _manager
    if _manager is None:
        _manager = TimescaleManager(
            host=os.getenv("TIMESCALEDB_HOST", "localhost"),
            port=int(os.getenv("TIMESCALEDB_PORT", "5432")),
            database=os.getenv("TIMESCALEDB_DATABASE", "sloscout"),
            user=os.getenv("TIMESCALEDB_USER", "sloscout"),
            password=os.getenv("TIMESCALEDB_PASSWORD", "changeme")
        )
    return _manager
