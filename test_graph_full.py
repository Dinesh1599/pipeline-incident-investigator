"""
Test the complete LangGraph workflow (all 12 nodes)
against the null-key failure scenario.

Requires:
    - .env.local with OPENAI_API_KEY, POSTGRES_*, AIRFLOW_*
    - Docker running (Airflow + Postgres)
    - The null-key scenario triggered (update run_id below)

Usage:
    python tests/test_graph_full.py
"""

import json
import logging

from dotenv import load_dotenv
load_dotenv(".env.local")

from agent.graph import compile_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)


def test_null_key_full():
    """Run the null-key scenario through the complete graph."""

    print("=" * 70)
    print("FULL END-TO-END TEST — Null Key Scenario")
    print("=" * 70)

    # UPDATE THIS with a real run_id from your Airflow UI
    trigger = {
        "pipeline_name": "sales_pipeline",
        "dag_id": "sales_pipeline",
        "task_id": "run_dbt_fct_sales",
        "run_id": "manual__2026-03-16T09:12:03.050328+00:00",  # <-- update
        "severity": "error",
        "error_message": "Bash command failed. The command returned a non-zero exit code 1.",
    }

    app = compile_graph()
    result = app.invoke(trigger)

    report = result.get("final_report", {})

    # ── Print the full report ───────────────────────────────
    print("\n" + "=" * 70)
    print("INVESTIGATION REPORT")
    print("=" * 70)

    print(f"\nIncident ID:  {report.get('incident_id')}")
    print(f"Severity:     {report.get('severity')}")
    print(f"Failure Class:{report.get('failure_class')}")
    print(f"Confidence:   {report.get('confidence')}")

    print(f"\n── What Failed ──")
    print(f"  {report.get('what_failed')}")

    print(f"\n── Where Failed ──")
    where = report.get("where_failed", {})
    print(f"  DAG:    {where.get('dag_id')}")
    print(f"  Task:   {where.get('task_id')}")
    print(f"  Model:  {where.get('model')}")
    print(f"  Table:  {where.get('table')}")
    print(f"  Column: {where.get('column')}")

    print(f"\n── How It Failed ──")
    print(f"  {report.get('how_it_failed')}")

    print(f"\n── Root Cause ──")
    print(f"  {report.get('root_cause')}")

    print(f"\n── Evidence Chain ──")
    for i, e in enumerate(report.get("evidence_chain", []), 1):
        print(f"  {i}. {e}")

    print(f"\n── Alternatives Considered ──")
    for alt in report.get("alternative_causes_considered", []):
        print(f"  - {alt.get('cause')}")
        print(f"    Ruled out by: {alt.get('ruled_out_by')}")

    print(f"\n── Fix ──")
    fix = report.get("fix", {})
    print(f"  Immediate:  {fix.get('immediate')}")
    print(f"  Preventive: {fix.get('preventive')}")
    print(f"  Monitoring: {fix.get('monitoring')}")

    print(f"\n── Prevention ──")
    for p in report.get("prevention", []):
        print(f"  - {p}")

    # ── Validation ──────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("VALIDATION")
    print(f"{'=' * 70}")

    checks = {
        "incident_id exists": bool(report.get("incident_id")),
        "failure_class is data_quality": report.get("failure_class") == "data_quality",
        "confidence > 0.7": report.get("confidence", 0) > 0.7,
        "root_cause mentions null or customer_id": (
            "null" in report.get("root_cause", "").lower()
            or "customer_id" in report.get("root_cause", "").lower()
        ),
        "evidence_chain not empty": len(report.get("evidence_chain", [])) > 0,
        "fix has immediate action": bool(fix.get("immediate")),
        "fix has preventive action": bool(fix.get("preventive")),
        "fix has monitoring action": bool(fix.get("monitoring")),
    }

    all_passed = True
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"  [{status}] {check}")

    print()
    if all_passed:
        print("ALL CHECKS PASSED — Investigation complete!")
    else:
        print("Some checks failed — review the report above.")

    # Save report to file
    with open("investigation_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to investigation_report.json")

    return result


if __name__ == "__main__":
    test_null_key_full()
