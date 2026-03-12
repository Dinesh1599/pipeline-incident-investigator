"""Test log parser - truncation and regex signal extraction."""

from agent.evidence.log_parser import (
    truncate_log,
    extract_signals_regex,
    extract_error_lines,
)


# Sample logs matching the three failure scenarios
NULL_KEY_LOG = """
[2026-03-11T02:05:00Z] INFO - Running with dbt=1.11.7
[2026-03-11T02:05:00Z] INFO - Registered adapter: postgres=1.10.0
[2026-03-11T02:05:00Z] INFO - Found 3 models, 5 seeds, 8 data tests, 2 sources
[2026-03-11T02:05:01Z] INFO - 1 of 1 START sql table model gold.fct_sales
[2026-03-11T02:05:01Z] INFO - 1 of 1 ERROR creating sql table model gold.fct_sales
[2026-03-11T02:05:01Z] INFO - Failure in model fct_sales (models/gold/fct_sales.sql)
[2026-03-11T02:05:01Z] INFO -   Database Error in model fct_sales (models/gold/fct_sales.sql)
[2026-03-11T02:05:01Z] INFO -   null value in column "customer_id" violates not-null constraint
[2026-03-11T02:05:01Z] INFO -   compiled code at target/run/sales_pipeline/models/gold/fct_sales.sql
[2026-03-11T02:05:01Z] ERROR - Task failed with exception
""".strip()

SCHEMA_DRIFT_LOG = """
[2026-03-11T02:05:00Z] INFO - Running with dbt=1.11.7
[2026-03-11T02:05:00Z] INFO - Found 3 models, 5 seeds, 8 data tests, 2 sources
[2026-03-11T02:05:01Z] INFO - 1 of 1 START sql table model silver.silver_customers
[2026-03-11T02:05:01Z] INFO - 1 of 1 ERROR creating sql table model silver.silver_customers
[2026-03-11T02:05:01Z] INFO - Failure in model silver_customers (models/silver/silver_customers.sql)
[2026-03-11T02:05:01Z] INFO -   Database Error in model silver_customers (models/silver/silver_customers.sql)
[2026-03-11T02:05:01Z] INFO -   invalid input syntax for type integer: "CUST-001"
[2026-03-11T02:05:01Z] ERROR - Task failed with exception
""".strip()

PERMISSION_LOG = """
[2026-03-11T02:05:00Z] INFO - Running with dbt=1.11.7
[2026-03-11T02:05:01Z] INFO - 1 of 1 START sql table model silver.silver_sales
[2026-03-11T02:05:01Z] ERROR - permission denied for schema bronze
[2026-03-11T02:05:01Z] ERROR - Task failed with exception
""".strip()


def test_truncate_log():
    print("── Log Truncation ──")

    # Short log — no truncation needed
    result = truncate_log(NULL_KEY_LOG)
    print(f"Short log lines: {len(result.splitlines())} (original: {len(NULL_KEY_LOG.splitlines())})")

    # Long log — generate a fake 200-line log with errors
    long_lines = [f"[2026-03-11T02:05:00Z] INFO - Processing row {i}" for i in range(200)]
    long_lines[50] = "[2026-03-11T02:05:00Z] ERROR - Something went wrong at row 50"
    long_lines[150] = "[2026-03-11T02:05:00Z] FATAL - Critical failure at row 150"
    long_log = "\n".join(long_lines)

    result = truncate_log(long_log)
    result_lines = len(result.splitlines())
    print(f"Long log truncated: {len(long_lines)} → {result_lines} lines")
    assert result_lines < len(long_lines), "Truncation should reduce line count"
    assert "ERROR" in result, "Error lines should be preserved"
    assert "FATAL" in result, "Fatal lines should be preserved"
    print()


def test_extract_signals_regex():
    print("── Regex Signal Extraction ──")

    # Null key scenario
    print("Null key log:")
    signals = extract_signals_regex(NULL_KEY_LOG)
    print(f"  error_type: {signals['error_type']}")
    print(f"  sql_state: {signals['sql_state_code']}")
    print(f"  columns: {signals['objects_referenced']['columns']}")
    print(f"  models: {signals['objects_referenced']['models']}")
    assert signals["error_type"] == "not_null_violation"
    assert signals["sql_state_code"] == "23502"
    print()

    # Schema drift scenario
    print("Schema drift log:")
    signals = extract_signals_regex(SCHEMA_DRIFT_LOG)
    print(f"  error_type: {signals['error_type']}")
    print(f"  sql_state: {signals['sql_state_code']}")
    print(f"  models: {signals['objects_referenced']['models']}")
    assert signals["error_type"] == "type_cast_failure"
    print()

    # Permission denied scenario
    print("Permission denied log:")
    signals = extract_signals_regex(PERMISSION_LOG)
    print(f"  error_type: {signals['error_type']}")
    print(f"  sql_state: {signals['sql_state_code']}")
    assert signals["error_type"] == "permission_denied"
    print()


def test_extract_error_lines():
    print("── Error Line Extraction ──")

    lines = extract_error_lines(NULL_KEY_LOG)
    print(f"Error lines from null key log: {len(lines)}")
    for line in lines:
        print(f"  {line[:80]}")
    assert len(lines) > 0
    print()

    lines = extract_error_lines("")
    print(f"Empty log: {len(lines)} lines")
    assert len(lines) == 0
    print()


if __name__ == "__main__":
    test_truncate_log()
    test_extract_signals_regex()
    test_extract_error_lines()
    print("All log parser tests passed.")
