-- ============================================================
-- init_db.sql
-- Creates additional databases, tables, and enables pgvector
-- Mounted at /docker-entrypoint-initdb.d/01-init_db.sql
-- Runs automatically on first postgres container start
-- ============================================================

-- The default 'airflow' database is created by POSTGRES_DB env var.
-- Create the two additional databases here.

CREATE DATABASE pipeline_db;

-- Investigator database (incidents, evidence, vector embeddings)
CREATE DATABASE investigator_db;

-- ── pipeline_db setup ──────────────────────────────────────
\connect pipeline_db;

CREATE EXTENSION IF NOT EXISTS vector;

-- Create schemas for medallion layers
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- Bronze tables: all TEXT columns so raw data loads without errors.
-- Type casting happens in the silver dbt layer.
CREATE TABLE IF NOT EXISTS bronze.sales (
    order_id    TEXT,
    customer_id TEXT,
    order_date  TEXT,
    product     TEXT,
    quantity    TEXT,
    unit_price  TEXT
);

CREATE TABLE IF NOT EXISTS bronze.customers (
    customer_id     TEXT,
    customer_name   TEXT,
    email           TEXT,
    region          TEXT
);

-- ── investigator_db setup ──────────────────────────────────
\connect investigator_db;

CREATE EXTENSION IF NOT EXISTS vector;

-- Incidents table
CREATE TABLE IF NOT EXISTS incidents (
    incident_id         VARCHAR PRIMARY KEY,
    created_at          TIMESTAMP DEFAULT NOW(),
    severity            VARCHAR NOT NULL DEFAULT 'error',
    status              VARCHAR NOT NULL DEFAULT 'open',
    source              VARCHAR NOT NULL DEFAULT 'cli',
    pipeline_name       VARCHAR,
    dag_id              VARCHAR,
    task_id             VARCHAR,
    run_id              VARCHAR,
    failure_class       VARCHAR,
    issue_summary       TEXT,
    root_cause          TEXT,
    confidence          FLOAT,
    fix_summary         TEXT,
    prevention_summary  TEXT,
    evidence_json       JSONB,
    validated           BOOLEAN DEFAULT FALSE,
    embedding           vector(1536)
);

-- IVFFlat index for vector similarity search
-- lists=10 is appropriate for < 1000 records (POC scale)
CREATE INDEX IF NOT EXISTS idx_incidents_embedding
    ON incidents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- Evidence table
CREATE TABLE IF NOT EXISTS incident_evidence (
    evidence_id     SERIAL PRIMARY KEY,
    incident_id     VARCHAR REFERENCES incidents(incident_id),
    evidence_type   VARCHAR NOT NULL,
    source_name     VARCHAR,
    reference_key   VARCHAR,
    evidence_text   TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Metadata snapshots for drift detection
CREATE TABLE IF NOT EXISTS metadata_snapshots (
    snapshot_id     SERIAL PRIMARY KEY,
    object_type     VARCHAR NOT NULL,
    object_name     VARCHAR NOT NULL,
    schema_name     VARCHAR,
    snapshot_json   JSONB,
    captured_at     TIMESTAMP DEFAULT NOW()
);

-- Pipeline-to-object mapping
CREATE TABLE IF NOT EXISTS pipeline_object_mappings (
    mapping_id      SERIAL PRIMARY KEY,
    dag_id          VARCHAR NOT NULL,
    task_id         VARCHAR NOT NULL,
    dbt_model       VARCHAR,
    target_table    VARCHAR,
    source_tables   TEXT[]
);
