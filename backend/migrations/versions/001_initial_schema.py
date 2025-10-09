"""Initial schema with all tables, indexes, and TimescaleDB hypertables

Revision ID: 001
Revises:
Create Date: 2025-01-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Enable required PostgreSQL extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # Create ENUM types
    environment_enum = sa.Enum('prod', 'staging', 'dev', name='environment_enum')
    status_enum = sa.Enum('active', 'inactive', 'archived', name='status_enum')
    event_type_enum = sa.Enum('log', 'trace', 'metric', name='event_type_enum')
    severity_enum = sa.Enum('debug', 'info', 'warning', 'error', 'critical', name='severity_enum')
    threshold_variant_enum = sa.Enum('conservative', 'balanced', 'aggressive', name='threshold_variant_enum')
    artifact_type_enum = sa.Enum('prometheus_rule', 'grafana_dashboard', 'runbook', name='artifact_type_enum')
    artifact_status_enum = sa.Enum('draft', 'deployed', 'rolled_back', name='artifact_status_enum')

    environment_enum.create(op.get_bind())
    status_enum.create(op.get_bind())
    event_type_enum.create(op.get_bind())
    severity_enum.create(op.get_bind())
    threshold_variant_enum.create(op.get_bind())
    artifact_type_enum.create(op.get_bind())
    artifact_status_enum.create(op.get_bind())

    # Create base tables (no foreign keys)

    # Services table
    op.create_table(
        'services',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('environment', environment_enum, nullable=False),
        sa.Column('owner_team', sa.String(length=255), nullable=False),
        sa.Column('telemetry_endpoints', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('label_mappings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('status', status_enum, nullable=False, server_default='active'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'environment', name='uq_services_name_environment')
    )

    # Policies table
    op.create_table(
        'policies',
        sa.Column('policy_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('blast_radius_threshold', sa.DECIMAL(precision=3, scale=2), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('policy_id'),
        sa.UniqueConstraint('name', name='uq_policies_name'),
        sa.CheckConstraint('blast_radius_threshold >= 0 AND blast_radius_threshold <= 1', name='ck_policies_blast_radius_threshold')
    )

    # Create dependent tables (with foreign keys)

    # TelemetryEvents table (will be converted to hypertable)
    op.create_table(
        'telemetry_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', event_type_enum, nullable=False),
        sa.Column('timestamp', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('severity', severity_enum, nullable=False, server_default='info'),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.Column('span_id', sa.String(length=32), nullable=True),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('raw_blob_s3_key', sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint('event_id', 'timestamp'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE')
    )

    # UserJourneys table
    op.create_table(
        'user_journeys',
        sa.Column('journey_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('entry_points', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('critical_path', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('confidence_score', sa.DECIMAL(precision=4, scale=3), nullable=False),
        sa.Column('discovered_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('journey_id'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='ck_user_journeys_confidence_score')
    )

    # Capsules table (will be converted to hypertable)
    op.create_table(
        'capsules',
        sa.Column('capsule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('journey_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('fingerprint_hash', sa.String(length=64), nullable=False),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('event_count', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('window_start', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('window_end', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('sample_events', postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.PrimaryKeyConstraint('capsule_id', 'window_start'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journey_id'], ['user_journeys.journey_id'], ondelete='SET NULL'),
        sa.CheckConstraint('window_end > window_start', name='ck_capsules_window_end'),
        sa.CheckConstraint('event_count > 0', name='ck_capsules_event_count')
    )

    # SLIs table
    op.create_table(
        'slis',
        sa.Column('sli_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('journey_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('promql_query', sa.Text(), nullable=False),
        sa.Column('confidence_score', sa.DECIMAL(precision=4, scale=3), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('approved_by', sa.String(length=255), nullable=True),
        sa.Column('approved_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('sli_id'),
        sa.ForeignKeyConstraint(['journey_id'], ['user_journeys.journey_id'], ondelete='CASCADE'),
        sa.CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='ck_slis_confidence_score'),
        sa.CheckConstraint(
            '(approved = true AND approved_by IS NOT NULL AND approved_at IS NOT NULL) OR (approved = false)',
            name='ck_slis_approval_consistency'
        )
    )

    # SLOs table
    op.create_table(
        'slos',
        sa.Column('slo_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('sli_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('target_percentage', sa.DECIMAL(precision=5, scale=2), nullable=False),
        sa.Column('time_window', sa.String(length=50), nullable=False),
        sa.Column('threshold_variant', threshold_variant_enum, nullable=False, server_default='balanced'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('slo_id'),
        sa.ForeignKeyConstraint(['sli_id'], ['slis.sli_id'], ondelete='CASCADE'),
        sa.CheckConstraint('target_percentage >= 0 AND target_percentage <= 100', name='ck_slos_target_percentage')
    )

    # Artifacts table
    op.create_table(
        'artifacts',
        sa.Column('artifact_id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('slo_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('artifact_type', artifact_type_enum, nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('confidence_score', sa.DECIMAL(precision=4, scale=3), nullable=False),
        sa.Column('status', artifact_status_enum, nullable=False, server_default='draft'),
        sa.Column('pr_url', sa.String(length=512), nullable=True),
        sa.Column('deployed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('artifact_id'),
        sa.ForeignKeyConstraint(['slo_id'], ['slos.slo_id'], ondelete='CASCADE'),
        sa.CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='ck_artifacts_confidence_score'),
        sa.CheckConstraint(
            "(status = 'deployed' AND deployed_at IS NOT NULL) OR (status != 'deployed')",
            name='ck_artifacts_deployed_consistency'
        )
    )

    # Convert to TimescaleDB hypertables
    op.execute("""
        SELECT create_hypertable(
            'telemetry_events',
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        )
    """)

    op.execute("""
        SELECT create_hypertable(
            'capsules',
            'window_start',
            chunk_time_interval => INTERVAL '1 hour',
            if_not_exists => TRUE
        )
    """)

    # Create indexes

    # Services indexes
    op.create_index('idx_services_status_environment', 'services', ['status', 'environment'])

    # TelemetryEvents indexes
    op.create_index('idx_telemetry_service_time', 'telemetry_events', ['service_id', sa.text('timestamp DESC')])
    op.create_index('idx_telemetry_trace_id', 'telemetry_events', ['trace_id'],
                    postgresql_where=sa.text('trace_id IS NOT NULL'))
    op.create_index('idx_telemetry_event_type_time', 'telemetry_events', ['event_type', sa.text('timestamp DESC')])

    # Capsules indexes
    op.create_index('idx_capsules_fingerprint', 'capsules', ['fingerprint_hash'])
    op.create_index('idx_capsules_service_journey', 'capsules', ['service_id', 'journey_id'])
    op.create_index('idx_capsules_service_window', 'capsules', ['service_id', sa.text('window_start DESC')])
    op.create_index('idx_capsules_journey_window', 'capsules', ['journey_id', sa.text('window_start DESC')],
                    postgresql_where=sa.text('journey_id IS NOT NULL'))

    # UserJourneys indexes
    op.create_index('idx_journeys_service_discovered', 'user_journeys', ['service_id', sa.text('discovered_at DESC')])
    op.create_index('idx_journeys_confidence', 'user_journeys', [sa.text('confidence_score DESC')])

    # SLIs indexes
    op.create_index('idx_slis_journey_approved', 'slis', ['journey_id', 'approved'])
    op.create_index('idx_slis_approved_by', 'slis', ['approved_by'],
                    postgresql_where=sa.text('approved_by IS NOT NULL'))
    op.create_index('idx_slis_confidence', 'slis', [sa.text('confidence_score DESC')])
    op.create_index('idx_slis_created', 'slis', [sa.text('created_at DESC')])

    # SLOs indexes
    op.create_index('idx_slos_sli', 'slos', ['sli_id'])
    op.create_index('idx_slos_threshold', 'slos', ['threshold_variant'])
    op.create_index('idx_slos_created', 'slos', [sa.text('created_at DESC')])

    # Artifacts indexes
    op.create_index('idx_artifacts_slo_status', 'artifacts', ['slo_id', 'status'])
    op.create_index('idx_artifacts_status_deployed', 'artifacts', ['status', sa.text('deployed_at DESC')])
    op.create_index('idx_artifacts_type', 'artifacts', ['artifact_type'])
    op.create_index('idx_artifacts_created', 'artifacts', [sa.text('created_at DESC')])

    # Policies indexes
    op.create_index('idx_policies_enabled', 'policies', ['enabled'],
                    postgresql_where=sa.text('enabled = true'))

    # Add retention policy to telemetry_events (7 days per NFR-008)
    op.execute("""
        SELECT add_retention_policy('telemetry_events', INTERVAL '7 days')
    """)

    # Seed default policies
    op.execute("""
        INSERT INTO policies (policy_id, name, description, blast_radius_threshold, enabled) VALUES
            (gen_random_uuid(), 'default-blast-radius', 'Block deployments affecting >70% of services', 0.70, true),
            (gen_random_uuid(), 'critical-service-protection', 'Block any changes to critical services without manual approval', 0.00, true)
    """)


def downgrade():
    # Remove retention policy first
    op.execute("SELECT remove_retention_policy('telemetry_events', if_exists => true)")

    # Drop tables in reverse dependency order
    op.drop_table('artifacts')
    op.drop_table('slos')
    op.drop_table('slis')
    op.drop_table('capsules')
    op.drop_table('user_journeys')
    op.drop_table('telemetry_events')
    op.drop_table('policies')
    op.drop_table('services')

    # Drop ENUM types in reverse order
    sa.Enum(name='artifact_status_enum').drop(op.get_bind())
    sa.Enum(name='artifact_type_enum').drop(op.get_bind())
    sa.Enum(name='threshold_variant_enum').drop(op.get_bind())
    sa.Enum(name='severity_enum').drop(op.get_bind())
    sa.Enum(name='event_type_enum').drop(op.get_bind())
    sa.Enum(name='status_enum').drop(op.get_bind())
    sa.Enum(name='environment_enum').drop(op.get_bind())
