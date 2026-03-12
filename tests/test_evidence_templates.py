"""Test evidence query templates against pipeline_db."""

from dotenv import load_dotenv
load_dotenv(".env.local")

from agent.connectors.postgres_connector import PostgresConnector
from agent.evidence.query_templates import (
    run_evidence_check,
    run_checks_for_class,
    run_upstream_checks,
)


def test_evidence_templates():
    pc = PostgresConnector()

    # Individual template checks
    print("── Individual Template Checks ──")

    result = run_evidence_check(pc, "row_count", {"schema": "bronze", "table": "sales"})
    print(f"row_count bronze.sales: {result['rows']}")

    result = run_evidence_check(pc, "null_check", {"schema": "bronze", "table": "sales", "column": "customer_id"})
    print(f"null_check bronze.sales.customer_id: {result['rows']}")

    result = run_evidence_check(pc, "duplicate_check", {"schema": "bronze", "table": "sales", "column": "order_id"})
    print(f"duplicate_check bronze.sales.order_id: {result['rows']}")

    result = run_evidence_check(pc, "column_presence", {"schema": "bronze", "table": "sales"})
    print(f"column_presence bronze.sales: {result['row_count']} columns")

    result = run_evidence_check(pc, "invalid_cast_check", {"schema": "bronze", "table": "sales", "column": "customer_id"})
    print(f"invalid_cast bronze.sales.customer_id: {result['rows']}")
    print()

    # Run checks for a failure class
    print("── Checks for data_quality Class ──")
    target = {
        "schema": "bronze",
        "table": "sales",
        "column": "customer_id",
        "timestamp_column": "order_date",
    }
    results = run_checks_for_class(pc, "data_quality", target)
    for r in results:
        print(f"  {r['template']:20s} → rows={r['row_count']} error={r['error']}")
    print()

    # Run checks for schema_drift class
    print("── Checks for schema_drift Class ──")
    target = {"schema": "bronze", "table": "sales", "column": "customer_id"}
    results = run_checks_for_class(pc, "schema_drift", target)
    for r in results:
        print(f"  {r['template']:20s} → rows={r['row_count']} error={r['error']}")
    print()

    # Upstream checks
    print("── Upstream Checks ──")
    upstream = [{"schema": "bronze", "table_name": "sales"}]
    results = run_upstream_checks(pc, upstream, column="customer_id")
    for r in results:
        print(f"  {r['template']:20s} ({r.get('context', '')}) → {r['rows']}")
    print()

    # Test with a bad template name
    print("── Error Handling ──")
    result = run_evidence_check(pc, "nonexistent_template", {})
    print(f"bad template: {result['error']}")

    result = run_evidence_check(pc, "null_check", {"schema": "bronze", "table": "sales"})
    print(f"missing param: {result['error']}")

    print("\nAll evidence template tests passed.")


if __name__ == "__main__":
    test_evidence_templates()
