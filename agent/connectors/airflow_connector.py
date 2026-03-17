"""
airflow_connector.py — Fetches data from Airflow via REST API v2.

Provides:
    - Task logs (last N lines around failure + ERROR/WARNING lines)
    - Task instance metadata (state, retries, duration, etc.)
    - DAG structure (task list and dependencies)

"""

import os
import logging
from typing import Optional


import requests



logger = logging.getLogger(__name__)


class AirflowConnector:
    """Connects to Airflow REST API v2 to fetch logs, metadata, and DAG info."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("AIRFLOW_API_URL", "http://airflow-apiserver:8080")
        )
        self.username = username or os.environ.get("AIRFLOW_API_USER", "airflow")
        self.password = password or os.environ.get("AIRFLOW_API_PASSWORD", "airflow")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        # Airflow 3 uses token-based auth (basic auth was removed)
        self._authenticate()

    def _authenticate(self) -> None: # creates auth token for airflow api
        """Get a JWT token from Airflow 3's /auth/token endpoint."""
        try:
            response = requests.post(
                f"{self.base_url}/auth/token",
                json={"username": self.username, "password": self.password},
                timeout=10,
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            logger.info("Airflow API authenticated successfully")
        except requests.exceptions.RequestException as e:
            logger.error("Airflow API authentication failed: %s", e)

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to the Airflow API."""
        url = f"{self.base_url}/api/v2/{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error("Airflow API request failed: %s %s — %s", "GET", url, e)
            return {}

    def get_task_logs(
        self,
        dag_id: str,
        run_id: str,
        task_id: str,
        try_number: int = 0,
    ) -> str:
        """Fetch task logs for a specific task instance.

        Returns the raw log text. The log parser module handles
        truncation and extraction.
        """

        endpoint = (
            f"dags/{dag_id}/dagRuns/{run_id}/"
            f"taskInstances/{task_id}/logs/{try_number}"
        )
        url = f"{self.base_url}/api/v2/{endpoint}"
        try:
            response = self.session.get(
                url,
                params={"full_content": True},
                #headers={"Accept": "text/plain"},
                timeout=15,
            )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                payload = response.json()
                content = payload.get("content", [])
                if isinstance(content, list):
                    # Airflow 3 returns structured log entries
                    lines = []
                    for entry in content:
                        if isinstance(entry, dict):
                            ts = entry.get("timestamp", "")
                            level = entry.get("level", "info").upper()
                            event = entry.get("event", "")
                            if ts:
                                lines.append(f"[{ts}] {level} - {event}")
                            elif event:
                                lines.append(event)
                        else:
                            lines.append(str(entry))
                    return "\n".join(lines)
                elif isinstance(content, str):
                    return content
                return str(content)
            return response.text


        except requests.exceptions.RequestException as e:
            logger.error("Failed to fetch task logs: %s", e)
            return ""

    def get_task_instance(
        self,
        dag_id: str,
        run_id: str,
        task_id: str,
    ) -> dict:
        """Fetch metadata for a specific task instance.

        Returns: state, start_date, end_date, duration, try_number,
        max_tries, operator, etc.
        """
        endpoint = f"dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}"
        return self._get(endpoint)

    def get_dag_run(self, dag_id: str, run_id: str) -> dict:
        """Fetch metadata for a specific DAG run."""
        endpoint = f"dags/{dag_id}/dagRuns/{run_id}"
        return self._get(endpoint)

    def get_dag_details(self, dag_id: str) -> dict:
        """Fetch DAG definition details (tasks, schedule, etc.)."""
        endpoint = f"dags/{dag_id}/details"
        return self._get(endpoint)

    def get_task_instances_for_run(self, dag_id: str, run_id: str) -> list[dict]:
        """Fetch all task instances for a DAG run.

        Useful for checking upstream task statuses when investigating
        dependency failures.
        """
        endpoint = f"dags/{dag_id}/dagRuns/{run_id}/taskInstances"
        result = self._get(endpoint)
        return result.get("task_instances", [])

    def collect_context(
        self,
        dag_id: str,
        run_id: str,
        task_id: str,
    ) -> dict:
        """Collect all available Airflow context for an investigation.

        This is the main method called by the Context Collector node.
        Returns a dict with logs, task metadata, DAG run info, and
        upstream task statuses.
        """
        task_instance = self.get_task_instance(dag_id, run_id, task_id)
        try_number = task_instance.get("try_number", 0)
        logs = self.get_task_logs(dag_id, run_id, task_id, try_number = try_number)
        if not logs and try_number != 0:
            logs = self.get_task_logs(dag_id, run_id, task_id, try_number = 0)
        
        dag_run = self.get_dag_run(dag_id, run_id)
        dag_details = self.get_dag_details(dag_id)
        all_tasks = self.get_task_instances_for_run(dag_id, run_id)

        return {
            "logs_raw": logs,
            "logs_available": bool(logs),
            "task_instance": task_instance,
            "dag_run": dag_run,
            "dag_details": dag_details,
            "all_task_instances": all_tasks,
        }
