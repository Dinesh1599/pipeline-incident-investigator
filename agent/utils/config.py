"""
config.py — Centralized configuration for the investigator agent.

Blueprint reference: Section 15 (Model Routing Strategy)

Model routing:
    GPT-4o-mini for mechanical tasks (extraction, classification)
    GPT-4o for reasoning tasks (code inspection, root cause, fix generation)
"""

import os


# ── Model Routing ───────────────────────────────────────────────

MODELS = {
    "signal_extraction": "gpt-4o-mini",
    "classification": "gpt-4o-mini",
    "code_inspection": "gpt-4o",
    "root_cause_reasoning": "gpt-4o",
    "fix_generation": "gpt-4o",
    "embedding": "text-embedding-3-small",
}


# ── LLM Settings ───────────────────────────────────────────────

LLM_TEMPERATURE = 0.0  # Deterministic outputs for investigation
LLM_MAX_RETRIES = 2    # Retry on malformed JSON


# ── Database ────────────────────────────────────────────────────

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.environ.get("POSTGRES_USER", "airflow")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "airflow")
PIPELINE_DB = os.environ.get("PIPELINE_DB", "pipeline_db")
INVESTIGATOR_DB = os.environ.get("INVESTIGATOR_DB", "investigator_db")


# ── Airflow ─────────────────────────────────────────────────────

AIRFLOW_API_URL = os.environ.get("AIRFLOW_API_URL", "http://airflow-apiserver:8080")
AIRFLOW_API_USER = os.environ.get("AIRFLOW_API_USER", "airflow")
AIRFLOW_API_PASSWORD = os.environ.get("AIRFLOW_API_PASSWORD", "airflow")


# ── dbt ─────────────────────────────────────────────────────────

DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", "/dbt")


# ── Investigation ───────────────────────────────────────────────

SIMILAR_INCIDENTS_TOP_K = 3   # Number of similar incidents to retrieve
EVIDENCE_QUERY_TIMEOUT = 10   # Seconds before a SQL check times out
MAX_LOG_LINES = 50            # Tail lines to keep from Airflow logs
