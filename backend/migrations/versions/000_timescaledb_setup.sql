-- TimescaleDB Extension Setup
-- This script must be run before any Alembic migrations
-- Requires PostgreSQL 12+ with TimescaleDB 2.11+ installed

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pg_trgm for text search (optional, for future use)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Verify TimescaleDB installation
SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';
