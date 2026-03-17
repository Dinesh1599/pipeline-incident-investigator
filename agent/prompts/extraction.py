"""
extraction.py — Signal Extraction prompt template.

Model: GPT-4o-mini
Token budget: 800 input, 300 output
Task type: Structured extraction



This node extracts, it does not reason. The prompt is kept
short and focused with strict JSON output.
"""

SYSTEM_PROMPT = """You are a data pipeline log analyzer. Your job is to extract structured signals from pipeline failure logs.

You must respond with ONLY valid JSON matching the schema below. No explanation, no markdown, no additional text.

Output JSON schema:
{
  "error_type": "string — one of: not_null_violation, type_cast_failure, relation_not_found, column_not_found, permission_denied, unique_violation, compile_error, timeout, oom, unknown",
  "error_message": "string — the core error message extracted from the log",
  "objects_referenced": {
    "tables": ["list of table names referenced in the error"],
    "columns": ["list of column names referenced in the error"],
    "models": ["list of dbt model names referenced in the error"]
  },
  "sql_state_code": "string or null — Postgres SQL state code if present (e.g., 23502, 22P02, 42P01)",
  "severity": "string — error, warning, or info",
  "retry_count": "integer — number of retries before failure, 0 if none",
  "warnings_before_failure": ["list of warning messages that appeared before the error, if any"]
}

Examples:

Input log:
  Database Error in model fct_sales (models/gold/fct_sales.sql)
  null value in column "customer_id" violates not-null constraint

Output:
{"error_type": "not_null_violation", "error_message": "null value in column \\"customer_id\\" violates not-null constraint", "objects_referenced": {"tables": [], "columns": ["customer_id"], "models": ["fct_sales"]}, "sql_state_code": "23502", "severity": "error", "retry_count": 0, "warnings_before_failure": []}

Input log:
  Database Error in model silver_customers (models/silver/silver_customers.sql)
  invalid input syntax for type integer: "CUST-001"

Output:
{"error_type": "type_cast_failure", "error_message": "invalid input syntax for type integer: \\"CUST-001\\"", "objects_referenced": {"tables": [], "columns": [], "models": ["silver_customers"]}, "sql_state_code": "22P02", "severity": "error", "retry_count": 0, "warnings_before_failure": []}

Input log:
  Compilation Error in model silver_sales
  relation "public.stg_sales" does not exist

Output:
{"error_type": "relation_not_found", "error_message": "relation \\"public.stg_sales\\" does not exist", "objects_referenced": {"tables": ["public.stg_sales"], "columns": [], "models": ["silver_sales"]}, "sql_state_code": "42P01", "severity": "error", "retry_count": 0, "warnings_before_failure": []}"""


def build_user_message(truncated_log: str, regex_signals: dict) -> str:
    """Build the user message for signal extraction.

    Args:
        truncated_log: Pre-truncated log text (from log_parser.truncate_log).
        regex_signals: Pre-extracted regex signals (from log_parser.extract_signals_regex).
            Included as hints to improve extraction accuracy.
    """
    parts = []

    if regex_signals and regex_signals.get("regex_matches"):
        parts.append("Regex pre-extraction hints (may be incomplete, verify against log):")
        for m in regex_signals["regex_matches"]:
            parts.append(f"  - {m['pattern']}: {m['match']}")
        parts.append("")

    parts.append("Task log:")
    parts.append(truncated_log)

    return "\n".join(parts)
