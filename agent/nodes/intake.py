"""
intake.py — Node 1: Intake

Receives the trigger payload (from Airflow callback, CLI, or webhook).
Normalizes it into the standard incident context fields. Generates an
incident_id. Resolves the task-to-model mapping.

This is pure Python logic, no LLM call.

"""

import logging
import uuid
from datetime import datetime, timezone

from agent.state import InvestigationState

logger = logging.getLogger(__name__)

# Task-to-model mapping
# Convention: Airflow task 'run_dbt_<model>' maps to dbt model '<model>'
# Fallback mapping for cases where naming convention doesn't apply
TASK_MODEL_MAP = {
    "run_dbt_silver_sales": "silver_sales",
    "run_dbt_silver_customers": "silver_customers",
    "run_dbt_fct_sales": "fct_sales",
    "run_dbt_tests": None,  # Test task, no single model
    "ingest_raw_sales": None,  # Ingestion task, not a dbt model
    "ingest_raw_customers": None,
}


def resolve_dbt_model(task_id: str) -> str | None:
    """Resolve which dbt model a task executes.

    First checks the explicit mapping table, then falls back
    to naming convention: 'run_dbt_<model>' -> '<model>'
    """
    if task_id in TASK_MODEL_MAP:
        return TASK_MODEL_MAP[task_id]

    if task_id.startswith("run_dbt_"):
        return task_id[len("run_dbt_"):]

    return None


def generate_incident_id() -> str:
    """Generate a unique incident ID."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"INC-{timestamp}-{short_uuid}"


def intake_node(state: InvestigationState) -> dict:
    """Intake node — normalizes the trigger and resolves targeting.

    Reads: dag_id, task_id, run_id, pipeline_name, severity,
           error_message, question (all from trigger payload)
    Writes: incident_id, dbt_model
    """
    # Generate incident ID if not already set
    incident_id = state.get("incident_id") or generate_incident_id()

    # Resolve task to dbt model
    task_id = state.get("task_id", "")
    dbt_model = resolve_dbt_model(task_id)

    # Default pipeline name
    pipeline_name = state.get("pipeline_name") or state.get("dag_id", "unknown")

    # Default severity
    severity = state.get("severity", "error")

    logger.info(
        "[INTAKE] Incident %s created for %s.%s (model: %s)",
        incident_id,
        pipeline_name,
        task_id,
        dbt_model or "N/A",
    )

    return {
        "incident_id": incident_id,
        "pipeline_name": pipeline_name,
        "severity": severity,
        "dbt_model": dbt_model,
    }
