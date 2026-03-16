"""
Test the first half of the LangGraph workflow (Nodes 1-5)
against the null-key failure scenario.

Runs: intake → context_collector → signal_extractor → classifier → router
Then hits placeholder nodes for the rest.

Requires:
    - .env.local with OPENAI_API_KEY, POSTGRES_*, AIRFLOW_*
    - Docker running (Airflow + Postgres)
    - The null-key scenario triggered at least once (for logs)

Usage:
    python tests/test_graph_first_half.py
"""

import json
import logging
import os
from dotenv import load_dotenv
load_dotenv(".env.local")

from agent.graph import compile_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)


# print("\n")
# print(f"URL: {os.environ.get('AIRFLOW_API_URL')}")
# print(f"USER: {os.environ.get('AIRFLOW_API_USER')}")
# print(f"PASS: {os.environ.get('AIRFLOW_API_PASSWORD')}")
# print("\n")


def test_airflow_connection():
    """Test the Airflow connection."""
    
    import requests

    session = requests.Session()
    session.auth = ("airflow", "airflow")
    session.headers.update({"Content-Type": "application/json"})

    response = session.get("http://localhost:8080/api/v2/version")
    print(f"Session status: {response.status_code}")


def test_null_key_scenario():
    """Run the null-key scenario through the first half of the graph."""

    print("=" * 60)
    print("Testing LangGraph Workflow — Null Key Scenario")
    print("=" * 60)

    # Simulate the trigger payload from Airflow failure callback
    trigger = {
        "pipeline_name": "sales_pipeline",
        "dag_id": "sales_pipeline",
        "task_id": "run_dbt_fct_sales",
        "run_id": "manual__2026-03-16T09:12:03.050328+00:00",  # Update with a real run_id
        "severity": "error",
        "error_message": "Bash command failed. The command returned a non-zero exit code 1.",
    }

    print(f"\nTrigger: {json.dumps(trigger, indent=2)}")
    print()

    # Compile and run the graph
    app = compile_graph()
    result = app.invoke(trigger)

    #print("\n\n\n","RESULT","\n", result, "\n\n\n","RESULT END") # <---- Delete Later.

    # Print results from each node
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print(f"\n── Intake ──")
    print(f"  incident_id: {result.get('incident_id')}")
    print(f"  dbt_model: {result.get('dbt_model')}")

    print(f"\n── Context Collector ──")
    print(f"  logs_available: {result.get('logs_available')}")
    print(f"  log_lines: {len(result.get('logs_raw', ''))}")
    print(f"  dbt_manifest: {'found' if result.get('dbt_manifest_entry') else 'not found'}")
    print(f"  code_context: {len(result.get('code_context', ''))} lines")
    print(f"  lineage: {result.get('lineage_context', {})}")
    print(f"  db_metadata_tables: {list(result.get('database_metadata', {}))}")

    print(f"\n── Signal Extractor ──")
    signals = result.get("extracted_signals", {})
    print(f"  error_type: {signals.get('error_type')}")
    print(f"  error_message: {signals.get('error_message', '')[:100]}")
    print(f"  sql_state: {signals.get('sql_state_code')}")
    print(f"  objects: {signals.get('objects_referenced', {})}")
    print(f"  target_objects: {result.get('target_objects', {})}")

    print(f"\n── Classifier ──")
    print(f"  failure_class: {result.get('failure_class')}")
    print(f"  secondary_class: {result.get('secondary_class')}")
    print(f"  confidence: {result.get('classification_confidence')}")
    print(f"  priorities: {result.get('investigation_priorities')}")

    # Validation
    print(f"\n── Validation ──")
    checks = {
        "incident_id exists": bool(result.get("incident_id")),
        "dbt_model is fct_sales": result.get("dbt_model") == "fct_sales",
        "signals extracted": bool(result.get("extracted_signals")),
        "failure_class is data_quality": result.get("failure_class") == "data_quality",
        "confidence > 0.5": (result.get("classification_confidence", 0) > 0.5),
    }

    all_passed = True
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"  [{status}] {check}")

    print()
    if all_passed:
        print("All checks passed!")
    else:
        print("Some checks failed — review the output above.")

    return result


def test_question_scenario():
    """Run the missing-partition scenario via a user question."""

    print("\n" + "=" * 60)
    print("Testing LangGraph Workflow — Question Scenario")
    print("=" * 60)

    trigger = {
        "pipeline_name": "sales_pipeline",
        "dag_id": "sales_pipeline",
        "task_id": "run_dbt_fct_sales",
        "run_id": "",
        "severity": "warning",
        "question": "Why are sales missing for March 4th?",
    }

    print(f"\nTrigger: {json.dumps(trigger, indent=2)}")
    print()

    app = compile_graph()
    result = app.invoke(trigger)

    print(f"\n── Classifier ──")
    print(f"  failure_class: {result.get('failure_class')}")
    print(f"  confidence: {result.get('classification_confidence')}")
    print(f"  priorities: {result.get('investigation_priorities')}")

    # For question scenarios, expect silent_correctness or dependency
    fc = result.get("failure_class", "")
    if fc in ("silent_correctness", "dependency"):
        print(f"\n  [PASS] Classification is reasonable: {fc}")
    else:
        print(f"\n  [NOTE] Got {fc} — expected silent_correctness or dependency")

    return result


if __name__ == "__main__":
    test_null_key_scenario()
    test_question_scenario()
    #test_airflow_connection()

