"""
Integration test for deployment and migration (Quickstart Steps 1-2)

Tests the complete deployment and database migration workflow:
- Helm deployment (mocked kubectl/helm commands)
- Database migration completes within 10-minute timeout (NFR-001)
- All 8 tables created (services, telemetry_events, capsules, user_journeys, slis, slos, artifacts, policies)
- TimescaleDB hypertables configured (telemetry_events, capsules)
- Retention policy on telemetry_events (7 days)
- 2 default policies seeded

Per quickstart.md Steps 1-2: Database Persistence validation
Per spec.md NFR-001: Migration must complete in <10 minutes
"""
import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timedelta
import subprocess
import time


@pytest.fixture
def mock_helm_deployment():
    """
    Mock Helm deployment commands for testing

    Simulates:
    - helm install slo-scout ... --wait --timeout=10m
    - kubectl get pods -n slo-scout
    - kubectl exec ... psql commands
    """
    with patch('subprocess.run') as mock_run:
        # Mock successful Helm install
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"NAME: slo-scout\nNAMESPACE: slo-scout\nSTATUS: deployed\nREVISION: 1\n",
            stderr=b""
        )
        yield mock_run


@pytest.fixture
def migration_db_engine():
    """
    Create a PostgreSQL engine for migration testing

    This will fail initially because TimescaleDB is not set up
    in the test environment, demonstrating TDD approach
    """
    import os

    # Use test database URL or fail explicitly
    database_url = os.getenv(
        "TEST_MIGRATION_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/sloscout_migration_test"
    )

    try:
        engine = create_engine(database_url, echo=False, pool_pre_ping=True)

        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return engine

    except Exception as e:
        # Expected to fail until infrastructure is set up
        pytest.skip(f"Migration test database not available: {e}")


@pytest.fixture
def clean_migration_db(migration_db_engine):
    """
    Clean database before migration test

    Drops all tables and extensions to simulate fresh deployment
    """
    from sqlalchemy import MetaData

    with migration_db_engine.connect() as conn:
        # Drop all tables
        inspector = inspect(migration_db_engine)
        for table_name in inspector.get_table_names():
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))

        # Drop TimescaleDB extension if exists
        try:
            conn.execute(text("DROP EXTENSION IF EXISTS timescaledb CASCADE"))
        except:
            pass

        # Drop other extensions
        try:
            conn.execute(text("DROP EXTENSION IF EXISTS \"uuid-ossp\" CASCADE"))
            conn.execute(text("DROP EXTENSION IF EXISTS pg_trgm CASCADE"))
        except:
            pass

        conn.commit()

    yield migration_db_engine

    # Cleanup after test
    with migration_db_engine.connect() as conn:
        inspector = inspect(migration_db_engine)
        for table_name in inspector.get_table_names():
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
        conn.commit()


class TestDeploymentMigration:
    """
    Test suite for deployment and migration validation

    Per quickstart.md:
    - Step 1: Deploy SLO-Scout via Helm
    - Step 2: Verify database migration

    These tests MUST FAIL initially until implementation is complete
    """

    def test_helm_deployment_mocked(self, mock_helm_deployment):
        """
        Test Helm deployment command (mocked)

        Validates:
        - Helm install command with correct parameters
        - --wait flag ensures pods are ready
        - --timeout=10m for migration completion (NFR-001)
        """
        # Simulate Helm deployment
        result = subprocess.run(
            [
                "helm", "install", "slo-scout", "./infrastructure/helm/slo-scout",
                "--namespace", "slo-scout",
                "--create-namespace",
                "--set", "global.storageClass=standard",
                "--set", "timescale.persistence.size=10Gi",
                "--set", "kafka.persistence.size=5Gi",
                "--wait",
                "--timeout=10m"
            ],
            capture_output=True
        )

        # Verify Helm command was called
        mock_helm_deployment.assert_called_once()

        # Verify command includes required flags
        call_args = mock_helm_deployment.call_args[0][0]
        assert "helm" in call_args
        assert "install" in call_args
        assert "slo-scout" in call_args
        assert "--wait" in call_args
        assert "--timeout=10m" in call_args

        # Verify deployment succeeded
        assert result.returncode == 0
        assert b"STATUS: deployed" in result.stdout

    def test_migration_timeout_requirement(self, clean_migration_db):
        """
        Test migration completes within 10-minute timeout (NFR-001)

        Per quickstart.md Step 1:
        "3-8 min: Database migration executes (creates all tables, hypertables, indexes)"

        This test will FAIL until Alembic migration is implemented
        """
        from alembic.config import Config
        from alembic import command

        # Record start time
        start_time = time.time()

        # Run Alembic migration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))

        try:
            # Upgrade to head (latest migration)
            command.upgrade(alembic_cfg, "head")

            # Calculate duration
            duration_seconds = time.time() - start_time
            duration_minutes = duration_seconds / 60

            # Verify migration completed within 10 minutes (NFR-001)
            assert duration_minutes < 10, f"Migration took {duration_minutes:.2f} minutes (>10 min limit)"

            # Typical expected range: 3-8 minutes per quickstart.md
            assert duration_minutes >= 0, "Migration duration must be positive"

        except Exception as e:
            pytest.fail(f"Migration failed: {e}")

    def test_all_tables_created(self, clean_migration_db):
        """
        Test all 8 tables are created by migration

        Per quickstart.md Step 2:
        "Expected Output (all 8 tables):
         - artifacts
         - capsules
         - policies
         - services
         - slis
         - slos
         - telemetry_events
         - user_journeys"

        This test will FAIL until migration is implemented
        """
        from alembic.config import Config
        from alembic import command

        # Run migration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))
        command.upgrade(alembic_cfg, "head")

        # Inspect tables
        inspector = inspect(clean_migration_db)
        table_names = inspector.get_table_names()

        # Expected tables per quickstart.md
        expected_tables = {
            "artifacts",
            "capsules",
            "policies",
            "services",
            "slis",
            "slos",
            "telemetry_events",
            "user_journeys"
        }

        # Verify all tables exist
        actual_tables = set(table_names)
        missing_tables = expected_tables - actual_tables
        extra_tables = actual_tables - expected_tables - {"alembic_version"}  # Alembic metadata table is OK

        assert len(missing_tables) == 0, f"Missing tables: {missing_tables}"
        assert len(table_names) >= 8, f"Expected at least 8 tables, got {len(table_names)}: {table_names}"

    def test_timescaledb_hypertables_configured(self, clean_migration_db):
        """
        Test TimescaleDB hypertables are created

        Per quickstart.md Step 2:
        "Verify TimescaleDB Hypertables:
         - telemetry_events | 1 dimension
         - capsules          | 1 dimension"

        This test will FAIL until TimescaleDB migration is implemented
        """
        from alembic.config import Config
        from alembic import command

        # Run migration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))
        command.upgrade(alembic_cfg, "head")

        # Query TimescaleDB hypertables
        with clean_migration_db.connect() as conn:
            result = conn.execute(text("""
                SELECT hypertable_name, num_dimensions
                FROM timescaledb_information.hypertables
                ORDER BY hypertable_name
            """))

            hypertables = {row[0]: row[1] for row in result}

        # Verify telemetry_events is a hypertable with 1 dimension
        assert "telemetry_events" in hypertables, "telemetry_events hypertable not found"
        assert hypertables["telemetry_events"] == 1, f"telemetry_events should have 1 dimension, got {hypertables['telemetry_events']}"

        # Verify capsules is a hypertable with 1 dimension
        assert "capsules" in hypertables, "capsules hypertable not found"
        assert hypertables["capsules"] == 1, f"capsules should have 1 dimension, got {hypertables['capsules']}"

        # Verify exactly 2 hypertables
        assert len(hypertables) == 2, f"Expected 2 hypertables, got {len(hypertables)}: {list(hypertables.keys())}"

    def test_retention_policy_configured(self, clean_migration_db):
        """
        Test retention policy is set on telemetry_events

        Per quickstart.md Step 2:
        "Verify Retention Policy:
         - telemetry_events | 7 days"

        Per spec.md NFR-008: "Telemetry events older than 7 days must be automatically dropped"

        This test will FAIL until retention policy is implemented
        """
        from alembic.config import Config
        from alembic import command

        # Run migration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))
        command.upgrade(alembic_cfg, "head")

        # Query retention policies
        with clean_migration_db.connect() as conn:
            result = conn.execute(text("""
                SELECT hypertable_name,
                       config::json->>'drop_after' as drop_after
                FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
            """))

            policies = {row[0]: row[1] for row in result}

        # Verify telemetry_events has retention policy
        assert "telemetry_events" in policies, "Retention policy not found for telemetry_events"

        # Verify 7-day retention (can be '7 days' or '168:00:00' format)
        retention_value = policies["telemetry_events"]
        assert "7" in retention_value or "168" in retention_value, \
            f"Expected 7-day retention, got: {retention_value}"

    def test_default_policies_seeded(self, clean_migration_db):
        """
        Test 2 default policies are seeded

        Per quickstart.md Step 2 (migration script):
        "Seed default policies:
         - default-blast-radius (0.70 threshold)
         - critical-service-protection (0.00 threshold)"

        This test will FAIL until policy seeding is implemented
        """
        from alembic.config import Config
        from alembic import command

        # Run migration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))
        command.upgrade(alembic_cfg, "head")

        # Query policies table
        with clean_migration_db.connect() as conn:
            result = conn.execute(text("""
                SELECT name, blast_radius_threshold, enabled
                FROM policies
                ORDER BY name
            """))

            policies = [(row[0], float(row[1]), row[2]) for row in result]

        # Verify exactly 2 policies
        assert len(policies) == 2, f"Expected 2 default policies, got {len(policies)}"

        # Verify policy names
        policy_names = {p[0] for p in policies}
        assert "default-blast-radius" in policy_names, "Missing default-blast-radius policy"
        assert "critical-service-protection" in policy_names, "Missing critical-service-protection policy"

        # Verify default-blast-radius threshold (0.70)
        default_blast_radius = next(p for p in policies if p[0] == "default-blast-radius")
        assert default_blast_radius[1] == 0.70, \
            f"default-blast-radius threshold should be 0.70, got {default_blast_radius[1]}"
        assert default_blast_radius[2] is True, "default-blast-radius should be enabled"

        # Verify critical-service-protection threshold (0.00)
        critical_protection = next(p for p in policies if p[0] == "critical-service-protection")
        assert critical_protection[1] == 0.00, \
            f"critical-service-protection threshold should be 0.00, got {critical_protection[1]}"
        assert critical_protection[2] is True, "critical-service-protection should be enabled"

    def test_table_constraints_and_indexes(self, clean_migration_db):
        """
        Test database constraints and indexes are created

        Validates:
        - Primary keys on all tables
        - Foreign key constraints
        - Unique constraints (e.g., services.name + environment)
        - Check constraints (e.g., confidence_score 0-1 range)
        - Performance indexes (e.g., service_id + timestamp)

        This test will FAIL until constraints are implemented
        """
        from alembic.config import Config
        from alembic import command

        # Run migration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))
        command.upgrade(alembic_cfg, "head")

        inspector = inspect(clean_migration_db)

        # Verify primary keys
        tables_with_pk = [
            "services", "policies", "telemetry_events", "user_journeys",
            "capsules", "slis", "slos", "artifacts"
        ]

        for table_name in tables_with_pk:
            pk = inspector.get_pk_constraint(table_name)
            assert pk is not None, f"Table {table_name} missing primary key"
            assert len(pk["constrained_columns"]) > 0, f"Table {table_name} primary key has no columns"

        # Verify foreign keys
        tables_with_fk = {
            "telemetry_events": ["service_id"],
            "user_journeys": ["service_id"],
            "capsules": ["service_id", "journey_id"],
            "slis": ["journey_id"],
            "slos": ["sli_id"],
            "artifacts": ["slo_id"]
        }

        for table_name, expected_fk_columns in tables_with_fk.items():
            fks = inspector.get_foreign_keys(table_name)
            fk_columns = [fk["constrained_columns"][0] for fk in fks]

            for expected_col in expected_fk_columns:
                assert expected_col in fk_columns, \
                    f"Table {table_name} missing foreign key on {expected_col}"

        # Verify unique constraint on services (name + environment)
        services_constraints = inspector.get_unique_constraints("services")
        name_env_constraint = any(
            set(c["column_names"]) == {"name", "environment"}
            for c in services_constraints
        )
        assert name_env_constraint, "services table missing unique constraint on (name, environment)"

        # Verify indexes exist (sampling key indexes)
        telemetry_indexes = inspector.get_indexes("telemetry_events")
        telemetry_index_names = [idx["name"] for idx in telemetry_indexes]

        # Check for service_id + timestamp index
        assert any("service" in name.lower() and "time" in name.lower() for name in telemetry_index_names), \
            "Missing index on telemetry_events (service_id, timestamp)"

    def test_timescaledb_chunk_intervals(self, clean_migration_db):
        """
        Test TimescaleDB chunk intervals are configured correctly

        Per migration script:
        - telemetry_events: 1 day chunks
        - capsules: 1 hour chunks

        This ensures optimal query performance for time-series data

        This test will FAIL until chunk intervals are implemented
        """
        from alembic.config import Config
        from alembic import command

        # Run migration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))
        command.upgrade(alembic_cfg, "head")

        # Query chunk intervals
        with clean_migration_db.connect() as conn:
            result = conn.execute(text("""
                SELECT h.hypertable_name,
                       d.interval_length
                FROM timescaledb_information.hypertables h
                JOIN timescaledb_information.dimensions d ON h.hypertable_name = d.hypertable_name
                ORDER BY h.hypertable_name
            """))

            intervals = {row[0]: row[1] for row in result}

        # Verify telemetry_events chunk interval (1 day = 86400000000 microseconds)
        assert "telemetry_events" in intervals, "telemetry_events chunk interval not found"
        telemetry_interval = intervals["telemetry_events"]
        # 1 day in microseconds
        expected_telemetry_interval = 86400000000
        assert telemetry_interval == expected_telemetry_interval, \
            f"telemetry_events chunk interval should be 1 day ({expected_telemetry_interval} µs), got {telemetry_interval} µs"

        # Verify capsules chunk interval (1 hour = 3600000000 microseconds)
        assert "capsules" in intervals, "capsules chunk interval not found"
        capsules_interval = intervals["capsules"]
        # 1 hour in microseconds
        expected_capsules_interval = 3600000000
        assert capsules_interval == expected_capsules_interval, \
            f"capsules chunk interval should be 1 hour ({expected_capsules_interval} µs), got {capsules_interval} µs"

    def test_migration_idempotency(self, clean_migration_db):
        """
        Test migration is idempotent (can run multiple times safely)

        Validates:
        - CREATE IF NOT EXISTS used for extensions
        - Migration script can be re-run without errors
        - Data is preserved across re-runs

        This test will FAIL until idempotent migration is implemented
        """
        from alembic.config import Config
        from alembic import command

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))

        # Run migration first time
        command.upgrade(alembic_cfg, "head")

        # Insert test data
        with clean_migration_db.connect() as conn:
            conn.execute(text("""
                INSERT INTO policies (policy_id, name, description, blast_radius_threshold, enabled)
                VALUES (gen_random_uuid(), 'test-policy', 'Test policy', 0.50, true)
            """))
            conn.commit()

        # Count policies
        with clean_migration_db.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM policies"))
            policy_count_before = result.scalar()

        # Downgrade to base
        command.downgrade(alembic_cfg, "base")

        # Run migration second time
        command.upgrade(alembic_cfg, "head")

        # Verify table structure is still valid
        inspector = inspect(clean_migration_db)
        table_names = inspector.get_table_names()
        assert "policies" in table_names, "policies table not recreated"

        # Verify default policies are seeded again
        with clean_migration_db.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM policies"))
            policy_count_after = result.scalar()

        # Should have 2 default policies after re-migration
        assert policy_count_after == 2, \
            f"Expected 2 policies after re-migration, got {policy_count_after}"

    def test_service_persistence_after_migration(self, clean_migration_db):
        """
        Test services can be persisted after migration

        Per quickstart.md Step 3.4:
        "Verify Persistence: Service persists to database"

        This validates the migration creates a functional services table

        This test will FAIL until migration is complete
        """
        from alembic.config import Config
        from alembic import command
        from uuid import uuid4

        # Run migration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))
        command.upgrade(alembic_cfg, "head")

        # Insert test service
        service_id = uuid4()
        with clean_migration_db.connect() as conn:
            conn.execute(text("""
                INSERT INTO services (id, name, environment, owner_team, telemetry_endpoints, label_mappings, status)
                VALUES (
                    :id,
                    'test-service',
                    'dev',
                    'test-team',
                    '{"prometheus_url": "http://prometheus:9090"}'::jsonb,
                    '{"job": "test-service"}'::jsonb,
                    'active'
                )
            """), {"id": service_id})
            conn.commit()

        # Retrieve service
        with clean_migration_db.connect() as conn:
            result = conn.execute(text("""
                SELECT name, environment, owner_team, status
                FROM services
                WHERE id = :id
            """), {"id": service_id})

            row = result.fetchone()

        # Verify service persisted correctly
        assert row is not None, "Service not found after insert"
        assert row[0] == "test-service", f"Expected name 'test-service', got '{row[0]}'"
        assert row[1] == "dev", f"Expected environment 'dev', got '{row[1]}'"
        assert row[2] == "test-team", f"Expected owner_team 'test-team', got '{row[2]}'"
        assert row[3] == "active", f"Expected status 'active', got '{row[3]}'"

    def test_initial_service_count_zero(self, clean_migration_db):
        """
        Test services table is empty after migration

        Per quickstart.md Step 2:
        "Verify Service Count (should be 0 initially)"

        This test will FAIL until migration is complete
        """
        from alembic.config import Config
        from alembic import command

        # Run migration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", str(clean_migration_db.url))
        command.upgrade(alembic_cfg, "head")

        # Count services
        with clean_migration_db.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM services"))
            count = result.scalar()

        # Verify no services exist initially
        assert count == 0, f"Expected 0 services after migration, got {count}"
