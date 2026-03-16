import requests
from typing import Optional, Dict, Any
from urllib.parse import quote


class AirflowTriggerHelper:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._authenticate()

    def _authenticate(self) -> None:
        """Get JWT token from Airflow 3."""
        response = self.session.post(
            f"{self.base_url}/auth/token",
            json={"username": self.username, "password": self.password},
            timeout=10,
        )
        response.raise_for_status()

        token = response.json().get("access_token")
        if not token:
            raise ValueError("No access_token returned from Airflow")

        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v2/{endpoint.lstrip('/')}"
        response = self.session.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def get_latest_dag_run(
        self, dag_id: str, manual_only: bool = True, limit: int = 20
    ) -> Dict[str, Any]:
        """Fetch the latest DAG run, optionally only manual ones."""
        data = self._get(
            f"dags/{quote(dag_id, safe='')}/dagRuns",
            params={"limit": limit, "order_by": "-run_after"},
        )

        dag_runs = data.get("dag_runs", [])
        if not dag_runs:
            raise ValueError(f"No DAG runs found for dag_id={dag_id}")

        if manual_only:
            for run in dag_runs:
                if run.get("run_type") == "manual":
                    return run
            raise ValueError(f"No manual DAG runs found for dag_id={dag_id}")

        return dag_runs[0]

    def create_trigger(
        self,
        dag_id: str,
        task_id: str,
        pipeline_name: Optional[str] = None,
        severity: str = "error",
        error_message: str = "Bash command failed. The command returned a non-zero exit code 1.",
        manual_only: bool = True,
    ) -> Dict[str, Any]:
        """Create a trigger dict using the latest DAG run."""
        latest_run = self.get_latest_dag_run(dag_id=dag_id, manual_only=manual_only)

        trigger = {
            "pipeline_name": pipeline_name or dag_id,
            "dag_id": dag_id,
            "task_id": task_id,
            "run_id": latest_run["dag_run_id"],
            "severity": severity,
            "error_message": error_message,
        }
        return trigger

    def get_task_instance(self, dag_id: str, run_id: str, task_id: str) -> Dict[str, Any]:
        """Fetch task instance details, including try_number."""
        encoded_dag_id = quote(dag_id, safe="")
        encoded_run_id = quote(run_id, safe="")
        encoded_task_id = quote(task_id, safe="")

        return self._get(
            f"dags/{encoded_dag_id}/dagRuns/{encoded_run_id}/taskInstances/{encoded_task_id}"
        )

    def get_try_number_from_trigger(self, trigger: Dict[str, Any]) -> Dict[str, Any]:
        """Given a trigger, fetch the task instance and return try_number + state."""
        task_instance = self.get_task_instance(
            dag_id=trigger["dag_id"],
            run_id=trigger["run_id"],
            task_id=trigger["task_id"],
        )

        return {
            "trigger": trigger,
            "task_instance_id": task_instance.get("id"),
            "task_id": task_instance.get("task_id"),
            "dag_id": task_instance.get("dag_id"),
            "run_id": task_instance.get("dag_run_id"),
            "state": task_instance.get("state"),
            "try_number": task_instance.get("try_number", 0),
            "max_tries": task_instance.get("max_tries", 0),
        }


if __name__ == "__main__":
    helper = AirflowTriggerHelper(
        base_url="http://localhost:8080",
        username="airflow",
        password="airflow",
    )

    trigger = helper.create_trigger(
        dag_id="sales_pipeline",
        task_id="run_dbt_silver_sales",
        pipeline_name="sales_pipeline",
        severity="error",
        error_message="Bash command failed. The command returned a non-zero exit code 1.",
        manual_only=True,
    )

    print("Trigger created:")
    print(trigger)

    result = helper.get_try_number_from_trigger(trigger)

    print("\nTask instance result:")
    print(result)

    if result["try_number"] == 0:
        print(
            "\nNote: try_number is 0, so this task never actually ran. "
            "Check if the task state is 'upstream_failed' and inspect upstream tasks."
        )