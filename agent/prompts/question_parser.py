"""
question_parser.py — Question Parser prompt template.

Model: GPT-4o-mini
Token budget: 800 input, 300 output
Task type: Structured extraction from natural language questions

Dedicated prompt for question-based investigations. Extracts
investigation targets from free-form user questions about
pipeline data issues.

Key design: Table and column information is passed dynamically
from the database at runtime, not hardcoded. Works with any
medallion architecture (bronze → silver → gold).
"""

SYSTEM_PROMPT = """You are a data pipeline investigator. A user has asked a question about unexpected data in their pipeline. Your job is to extract structured investigation targets from their question.

You must respond with ONLY valid JSON matching the schema below. No explanation, no markdown.

{
  "investigation_type": "string — one of: missing_data, wrong_values, unexpected_duplicates, metric_anomaly, stale_data, row_count_mismatch, unknown",
  "description": "string — brief restatement of what the user is asking about",
  "tables_to_check": [
    {
      "schema": "string — database schema",
      "table": "string — table name",
      "layer": "string — bronze, silver, or gold"
    }
  ],
  "columns_of_interest": ["string — specific column names relevant to the question"],
  "date_filter": {
    "column": "string or null — date/timestamp column to filter on",
    "value": "string or null — specific date in ISO format YYYY-MM-DD",
    "range_start": "string or null — start date if a range is mentioned",
    "range_end": "string or null — end date if a range is mentioned"
  },
  "check_priorities": ["string — ordered list of evidence checks to run"]
}

## Pipeline Architecture

The pipeline follows a medallion architecture with three layers:

  bronze (raw ingested data) → silver (cleaned/typed data) → gold (aggregated facts)

The available schemas, tables, and columns will be provided in the user message under "Available pipeline tables." Use ONLY tables that exist in that list.

## Critical Rules

1. ALWAYS include tables from ALL relevant layers in tables_to_check, ordered from lowest (bronze) to highest (gold). This lets the investigator determine which layer the issue originates from.

2. Match the user's question to the relevant tables by looking at column names and table descriptions. For example, if the user asks about "sales" or "revenue", include tables that have sales-related columns across all layers.

3. columns_of_interest should include the SPECIFIC column names from the available tables. Map the user's business language to actual column names found in the table list.

4. check_priorities should be ordered by what's most likely to reveal the issue:
   - missing_data → partition_check, row_count, freshness
   - wrong_values → null_check, duplicate_check, row_count, invalid_cast_check
   - unexpected_duplicates → duplicate_check, row_count
   - metric_anomaly → row_count, duplicate_check, null_check
   - stale_data → freshness, row_count
   - row_count_mismatch → row_count, duplicate_check, partition_check

5. For date_filter, identify date/timestamp columns from the available tables. Use ISO format YYYY-MM-DD for specific dates."""


def build_user_message(
    question: str,
    pipeline_context: dict | None = None,
    available_tables: list[dict] | None = None,
) -> str:
    """Build the user message for question parsing.

    Args:
        question: The user's free-form question.
        pipeline_context: Optional dict with model name, upstream info.
        available_tables: List of dicts with schema, table, columns info
            discovered from the database at runtime.
    """
    parts = [f'User question: "{question}"']

    if available_tables:
        parts.append("")
        parts.append("Available pipeline tables:")
        for table_info in available_tables:
            schema = table_info.get("schema", "")
            table = table_info.get("table", "")
            columns = table_info.get("columns", [])
            layer = _infer_layer(schema)
            col_str = ", ".join(columns) if columns else "unknown columns"
            line = f"  [{layer}] {schema}.{table} — columns: {col_str}"
            date_range = table_info.get("date_range")
            if date_range:
                line += f" (data range: {date_range['min']} to {date_range['max']})"
            parts.append(line)

    if pipeline_context:
        parts.append("")
        parts.append("Pipeline context:")
        if pipeline_context.get("model"):
            parts.append(f"  Model being investigated: {pipeline_context['model']}")
        if pipeline_context.get("upstream_models"):
            parts.append(f"  Upstream models: {pipeline_context['upstream_models']}")
        if pipeline_context.get("upstream_sources"):
            parts.append(f"  Upstream sources: {pipeline_context['upstream_sources']}")

    return "\n".join(parts)


def _infer_layer(schema: str) -> str:
    """Infer the medallion layer from a schema name."""
    schema_lower = schema.lower()
    if "bronze" in schema_lower or "raw" in schema_lower or "staging" in schema_lower:
        return "bronze"
    elif "silver" in schema_lower or "clean" in schema_lower or "intermediate" in schema_lower:
        return "silver"
    elif "gold" in schema_lower or "mart" in schema_lower or "analytics" in schema_lower or "fact" in schema_lower:
        return "gold"
    return schema