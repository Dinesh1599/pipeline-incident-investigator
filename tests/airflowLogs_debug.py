from dotenv import load_dotenv
load_dotenv(".env.local")

import os
import requests

base_url = os.environ.get("AIRFLOW_API_URL", "http://localhost:8080")
username = os.environ.get("AIRFLOW_API_USER", "airflow")
password = os.environ.get("AIRFLOW_API_PASSWORD", "airflow")

# Get JWT token
auth_response = requests.post(
    f"{base_url}/auth/token",
    json={"username": username, "password": password},
)
token = auth_response.json().get("access_token")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Use a real run_id from your Airflow UI
dag_id = "sales_pipeline"
run_id = "manual__2026-03-16T09:12:03.050328+00:00"
task_id = "run_dbt_fct_sales"

# Get task instance first
ti_response = requests.get(
    f"{base_url}/api/v2/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}",
    headers=headers,
)
print("=== Task Instance ===")
print(f"Status: {ti_response.status_code}")
import json
ti_data = ti_response.json()
print(json.dumps(ti_data, indent=2, default=str))

try_number = ti_data.get("try_number", 0)
print(f"\ntry_number: {try_number}")

# Get logs
log_response = requests.get(
    f"{base_url}/api/v2/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}/logs/{try_number}",
    params={"full_content": True},
    headers=headers,
)
print("\n=== Logs Response ===")
print(f"Status: {log_response.status_code}")
print(f"Content-Type: {log_response.headers.get('Content-Type')}")
print(f"Response type: {type(log_response.json())}")
print(json.dumps(log_response.json(), indent=2, default=str)[:3000])