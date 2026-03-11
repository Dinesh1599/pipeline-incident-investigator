"""
failure_callback.py — Airflow on_failure_callback for the sales pipeline.

When a task fails, this callback captures the incident context (dag_id,
task_id, run_id, etc.) and posts it to the investigator-api. This is the
automatic trigger path described in blueprint Section 8 (Stage 1).

Placed in airflow/plugins/ so it is importable from DAG files.
"""

import json
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger("airflow.plugins.failure_callback")

INVESTIGATOR_API_URL = "http://investigator-api:8000/investigate"


def on_task_failure(context: dict) -> None:
    """Called by Airflow when a task fails."""

    task_instance = context.get("task_instance")
    dag_run = context.get("dag_run")
    exception = context.get("exception")

    payload = {
        "pipeline_name": task_instance.dag_id if task_instance else "unknown",
        "dag_id": task_instance.dag_id if task_instance else "unknown",
        "task_id": task_instance.task_id if task_instance else "unknown",
        "run_id": dag_run.run_id if dag_run else "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": "error",
        "error_message": str(exception) if exception else "Unknown error",
    }

    logger.error(
        "Task failure detected. Trigger payload:\n%s",
        json.dumps(payload, indent=2),
    )

    # Post to investigator-api (best-effort, don't block Airflow)
    try:
        response = requests.post(
            INVESTIGATOR_API_URL,
            json=payload,
            timeout=10,
        )
        logger.info(
            "Investigator API response: %s %s",
            response.status_code,
            response.text[:200],
        )
    except requests.exceptions.ConnectionError:
        logger.warning(
            "Investigator API not reachable at %s. "
            "Payload logged above for manual investigation.",
            INVESTIGATOR_API_URL,
        )
    except Exception as e:
        logger.warning("Failed to post to investigator API: %s", e)
