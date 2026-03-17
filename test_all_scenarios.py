"""
Test all three failure scenarios end-to-end.

Runs the complete graph for each scenario and scores the output
against the evaluation rubric from blueprint Section 16.

Requires:
    - .env.local configured
    - Docker running (Airflow + Postgres)
    - Scenarios triggered in Airflow (update run_ids below)

Usage:
    python tests/test_all_scenarios.py
"""

import json
import logging

from dotenv import load_dotenv
load_dotenv(".env.local")

from agent.graph import compile_graph

logging.basicConfig(level=logging.INFO, format="%(message)s")


# ── Expected outputs from blueprint Section 16 ──────────────────

SCENARIOS = {
    "null_join_key": {
        "trigger": {
            "pipeline_name": "sales_pipeline",
            "dag_id": "sales_pipeline",
            "task_id": "run_dbt_fct_sales",
            "run_id": "manual__2026-03-16T22:16:24.462604+00:00",  # <-- update
            "severity": "error",
            "error_message": "Bash command failed. The command returned a non-zero exit code 1.",
        },
        "expected": {
            "failure_class": "data_quality",
            "expected_table": ["bronze.sales", "silver_sales", "fct_sales"],
            "expected_column": "customer_id",
            "root_cause_keywords": ["null", "customer_id", "join"],
            "fix_should_mention": ["filter", "not_null", "WHERE"],
            "prevention_should_mention": ["test", "validation", "alert"],
        },
    },
    "schema_drift": {
        "trigger": {
            "pipeline_name": "sales_pipeline",
            "dag_id": "sales_pipeline",
            "task_id": "run_dbt_silver_customers",
            "run_id": "manual__2026-03-16T22:21:57.723073+00:00",  # <-- update
            "severity": "error",
            "error_message": "Bash command failed. The command returned a non-zero exit code 1.",
        },
        "expected": {
            "failure_class": "schema_drift",
            "expected_table": ["bronze.customers", "silver_customers"],
            "expected_column": "customer_id",
            "root_cause_keywords": ["type", "cast", "integer", "CUST", "format"],
            "fix_should_mention": ["safe", "cast", "TRY", "regex", "validation"],
            "prevention_should_mention": ["schema", "contract", "drift", "alert"],
        },
    },
    "missing_partition": {
        "trigger": {
            "pipeline_name": "sales_pipeline",
            "dag_id": "sales_pipeline",
            "task_id": "run_dbt_fct_sales",
            "run_id": "",  # Empty — triggered by question
            "severity": "warning",
            "question": "Why are sales missing for March 4th?",
        },
        "expected": {
            "failure_class": "silent_correctness",
            "expected_table": ["bronze.sales"],
            "expected_column": "order_date",
            "root_cause_keywords": ["missing", "march", "2026-03-04", "partition", "zero", "no data"],
            "fix_should_mention": ["completeness", "check", "date", "row"],
            "prevention_should_mention": ["alert", "monitor", "zero"],
        },
    },
}


def score_scenario(name: str, report: dict, expected: dict) -> dict:
    """Score a scenario against the evaluation rubric.

    Blueprint Section 16 scoring:
        Classification correct      — 1.0
        Table/model identified       — 1.0
        Column identified            — 1.0
        Root cause accurate          — 1.0
        Fix is actionable            — 1.0
        Prevention is reasonable     — 1.0
        Total                        — 6.0
    """
    scores = {}

    # 1. Classification correct
    if report.get("failure_class") == expected["failure_class"]:
        scores["classification"] = 1.0
    elif report.get("failure_class") in ["data_quality", "dependency"] and expected["failure_class"] == "silent_correctness":
        scores["classification"] = 0.5  # Close enough for ambiguous scenario
    else:
        scores["classification"] = 0.0

    # 2. Table/model identified
    where = report.get("where_failed", {})
    root_cause = report.get("root_cause", "").lower()
    evidence_text = " ".join(report.get("evidence_chain", [])).lower()
    all_text = f"{root_cause} {evidence_text}"

    table_found = any(t.lower() in all_text for t in expected["expected_table"])
    scores["table_identified"] = 1.0 if table_found else 0.0

    # 3. Column identified
    col = expected.get("expected_column", "")
    col_found = col.lower() in all_text if col else True
    scores["column_identified"] = 1.0 if col_found else 0.0

    # 4. Root cause accurate
    keywords_found = sum(
        1 for kw in expected["root_cause_keywords"]
        if kw.lower() in root_cause
    )
    keyword_ratio = keywords_found / len(expected["root_cause_keywords"])
    if keyword_ratio >= 0.5:
        scores["root_cause"] = 1.0
    elif keyword_ratio >= 0.25:
        scores["root_cause"] = 0.5
    else:
        scores["root_cause"] = 0.0

    # 5. Fix is actionable
    fix = report.get("fix", {})
    fix_text = f"{fix.get('immediate', '')} {fix.get('preventive', '')}".lower()
    fix_keywords = sum(
        1 for kw in expected["fix_should_mention"]
        if kw.lower() in fix_text
    )
    if fix_keywords >= 2:
        scores["fix_actionable"] = 1.0
    elif fix_keywords >= 1:
        scores["fix_actionable"] = 0.5
    else:
        scores["fix_actionable"] = 0.0

    # 6. Prevention is reasonable
    prevention_text = fix_text + " " + " ".join(report.get("prevention", [])).lower()
    prevention_keywords = sum(
        1 for kw in expected["prevention_should_mention"]
        if kw.lower() in prevention_text
    )
    if prevention_keywords >= 2:
        scores["prevention"] = 1.0
    elif prevention_keywords >= 1:
        scores["prevention"] = 0.5
    else:
        scores["prevention"] = 0.0

    total = sum(scores.values())
    scores["total"] = total

    return scores


def run_scenario(name: str, scenario: dict) -> dict:
    """Run a single scenario and return the report."""
    print(f"\n{'=' * 70}")
    print(f"SCENARIO: {name}")
    print(f"{'=' * 70}")

    trigger = scenario["trigger"]

    # Skip if run_id placeholder not updated
    if "PASTE" in trigger.get("run_id", ""):
        print(f"  SKIPPED — update run_id in test_all_scenarios.py")
        return {}

    app = compile_graph()
    result = app.invoke(trigger)
    report = result.get("final_report", {})

    # Print summary
    print(f"\n  Class: {report.get('failure_class')}")
    print(f"  Confidence: {report.get('confidence')}")
    print(f"  Root cause: {report.get('root_cause', '')[:150]}")

    fix = report.get("fix", {})
    print(f"  Fix: {fix.get('immediate', '')[:100]}")

    return report


def main():
    print("=" * 70)
    print("EVALUATION — ALL SCENARIOS")
    print("=" * 70)

    results = {}
    scores = {}

    for name, scenario in SCENARIOS.items():
        report = run_scenario(name, scenario)
        if report:
            results[name] = report
            scores[name] = score_scenario(name, report, scenario["expected"])

    # ── Print scorecard ─────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("SCORECARD")
    print(f"{'=' * 70}")

    for name, score in scores.items():
        print(f"\n  {name}:")
        for criterion, value in score.items():
            if criterion != "total":
                status = "PASS" if value >= 1.0 else ("PARTIAL" if value >= 0.5 else "FAIL")
                print(f"    [{status}] {criterion}: {value}")
        print(f"    TOTAL: {score['total']}/6.0")

    if scores:
        overall = sum(s["total"] for s in scores.values()) / len(scores)
        print(f"\n  Overall average: {overall:.1f}/6.0")

        if overall >= 5.0:
            print("  EXCELLENT — Agent performs well across all scenarios")
        elif overall >= 4.0:
            print("  GOOD — Agent performs reasonably, some refinement needed")
        elif overall >= 3.0:
            print("  FAIR — Agent needs prompt iteration on weak areas")
        else:
            print("  NEEDS WORK — Review LangSmith traces for failing scenarios")

    # Save results
    with open("evaluation_results.json", "w") as f:
        json.dump({"results": results, "scores": scores}, f, indent=2, default=str)
    print(f"\nResults saved to evaluation_results.json")


if __name__ == "__main__":
    main()