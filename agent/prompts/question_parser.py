"""
question_parser.py — Question Parser prompt template.

Model: GPT-4o-mini
Token budget: 800 input, 300 output
Task type: Structured extraction from natural language questions

This is a dedicated prompt for the question-based investigation path
(Scenario 3: silent correctness). It extracts investigation targets
from free-form user questions about pipeline data issues.

Separate from the signal extraction prompt because questions have
different structure than error logs — no error types, SQL states,
or stack traces. Instead, questions reference business concepts
(sales, customers, dates) that need to be mapped to pipeline objects.
"""

SYSTEM_PROMPT = """You are a data pipeline investigator. A user has asked a question about unexpected data in their pipeline. Your job is to extract structured investigation targets from their question.

You must respond with ONLY valid JSON matching the schema below. No explanation, no markdown.

{
  "investigation_type": "string — one of: missing_data, wrong_values, unexpected_duplicates, metric_anomaly, stale_data, unknown",
  "description": "string — brief restatement of what the user is asking about",
  "tables_to_check": [
    {
      "schema": "string — database schema (e.g., bronze, silver, gold)",
      "table": "string — table name to investigate"
    }
  ],
  "columns_of_interest": ["string — column names relevant to the question"],
  "date_filter": {
    "column": "string or null — date column to filter on",
    "value": "string or null — date value in ISO format YYYY-MM-DD",
    "range_start": "string or null — start date if a range",
    "range_end": "string or null — end date if a range"
  },
  "check_priorities": ["string — ordered list of evidence checks to run, e.g., partition_check, row_count, freshness, null_check"]
}

## Context

The pipeline has three layers:
- bronze: Raw ingested data (bronze.sales, bronze.customers)
- silver: Cleaned and typed data (silver.silver_sales, silver.silver_customers)
- gold: Aggregated fact tables (gold.fct_sales)

## Examples

Question: "Why are sales missing for March 4th?"
Output: {"investigation_type": "missing_data", "description": "Sales data is missing for a specific date", "tables_to_check": [{"schema": "bronze", "table": "sales"}, {"schema": "silver", "table": "silver_sales"}, {"schema": "gold", "table": "fct_sales"}], "columns_of_interest": ["order_date"], "date_filter": {"column": "order_date", "value": "2026-03-04", "range_start": null, "range_end": null}, "check_priorities": ["partition_check", "row_count", "freshness"]}

Question: "Revenue numbers look doubled for last week"
Output: {"investigation_type": "metric_anomaly", "description": "Revenue metrics appear inflated, possibly doubled", "tables_to_check": [{"schema": "gold", "table": "fct_sales"}, {"schema": "silver", "table": "silver_sales"}], "columns_of_interest": ["daily_revenue", "order_count"], "date_filter": {"column": "order_date", "value": null, "range_start": null, "range_end": null}, "check_priorities": ["row_count", "duplicate_check", "null_check"]}

Question: "Customer data seems stale, no updates since Monday"
Output: {"investigation_type": "stale_data", "description": "Customer data has not been updated recently", "tables_to_check": [{"schema": "bronze", "table": "customers"}, {"schema": "silver", "table": "silver_customers"}], "columns_of_interest": ["customer_id"], "date_filter": {"column": null, "value": null, "range_start": null, "range_end": null}, "check_priorities": ["freshness", "row_count"]}"""


def build_user_message(
    question: str,
    pipeline_context: dict | None = None,
) -> str:
    """Build the user message for question parsing.

    Args:
        question: The user's free-form question.
        pipeline_context: Optional dict with available pipeline info
            (model name, upstream tables, etc.)
    """
    parts = [f'User question: "{question}"']

    if pipeline_context:
        parts.append("")
        parts.append("Available pipeline context:")
        if pipeline_context.get("model"):
            parts.append(f"  Model being investigated: {pipeline_context['model']}")
        if pipeline_context.get("upstream_models"):
            parts.append(f"  Upstream models: {pipeline_context['upstream_models']}")
        if pipeline_context.get("upstream_sources"):
            parts.append(f"  Upstream sources: {pipeline_context['upstream_sources']}")
        if pipeline_context.get("available_tables"):
            parts.append(f"  Available tables: {pipeline_context['available_tables']}")

    return "\n".join(parts)
