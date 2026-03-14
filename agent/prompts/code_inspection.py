"""
code_inspection.py — Code Inspection prompt template.

Model: GPT-4o
Token budget: 3000 input, 600 output
Task type: Targeted code review

Blueprint reference: Section 10.3

The prompt presents evidence FIRST, then the SQL code. This primes
the LLM to look for the specific issue rather than doing a generic
code review.
"""

SYSTEM_PROMPT = """You are a SQL code reviewer investigating a specific data pipeline failure. You are NOT doing a general code review. Focus ONLY on issues relevant to the current incident.

Given the failure context (error, classification, evidence) and the SQL model code, identify:
1. The specific code construct causing or contributing to the failure
2. Where in the SQL it occurs (line number or section)
3. Why it is relevant to this incident

Respond with ONLY valid JSON matching the schema. No explanation, no markdown.

{
  "findings": [
    {
      "location": "string — line number, section, or SQL construct (e.g., 'line 12', 'JOIN clause', 'WHERE filter')",
      "issue": "string — what the code issue is",
      "relevance": "string — why this is relevant to the current failure",
      "severity": "string — high, medium, or low"
    }
  ],
  "code_summary": "string — brief description of what this model does",
  "primary_finding": "string — the single most important finding related to the failure"
}

Example:

Error context: NOT NULL constraint violation on customer_id in fct_sales
Classification: data_quality

SQL:
  SELECT ss.customer_id, sc.customer_name, ss.order_date,
         COUNT(*) AS order_count, SUM(ss.total_amount) AS daily_revenue
  FROM silver.silver_sales ss
  LEFT JOIN silver.silver_customers sc ON ss.customer_id = sc.customer_id
  GROUP BY ss.customer_id, sc.customer_name, ss.order_date

Output:
{"findings": [{"location": "LEFT JOIN clause (line 4)", "issue": "LEFT JOIN preserves rows where customer_id is NULL in silver_sales. These NULL values pass through to the output.", "relevance": "NULL customer_id rows from silver_sales survive the LEFT JOIN and reach the INSERT, triggering the NOT NULL constraint on the target table.", "severity": "high"}, {"location": "Missing WHERE filter", "issue": "No WHERE clause filters out NULL customer_id before the join.", "relevance": "Adding WHERE ss.customer_id IS NOT NULL would prevent NULL rows from reaching the output.", "severity": "high"}], "code_summary": "Joins silver_sales with silver_customers and aggregates by customer and date to produce a fact table.", "primary_finding": "LEFT JOIN without null filter on customer_id allows NULL rows to propagate to the output, causing NOT NULL constraint violation."}"""


def build_user_message(
    failure_context: dict,
    classification: dict,
    evidence_results: list[dict],
    model_sql: str,
    model_name: str,
) -> str:
    """Build the user message for code inspection.

    Evidence is presented FIRST, then the SQL — this primes the LLM
    to look for the specific issue.

    Args:
        failure_context: Extracted signals from the Signal Extractor.
        classification: Output from the Classifier node.
        evidence_results: Results from the Database Evidence Analyzer.
        model_sql: The raw SQL of the dbt model.
        model_name: The dbt model name.
    """
    parts = []

    # Evidence first
    parts.append("== FAILURE CONTEXT ==")
    if failure_context.get("error_type"):
        parts.append(f"Error type: {failure_context['error_type']}")
    if failure_context.get("error_message"):
        parts.append(f"Error message: {failure_context['error_message']}")
    parts.append("")

    parts.append("== CLASSIFICATION ==")
    if classification:
        parts.append(f"Failure class: {classification.get('primary_class', 'unknown')}")
        parts.append(f"Reasoning: {classification.get('reasoning', '')}")
    parts.append("")

    if evidence_results:
        parts.append("== DATABASE EVIDENCE ==")
        for evidence in evidence_results:
            if evidence.get("error"):
                parts.append(f"  {evidence['template']}: ERROR — {evidence['error']}")
            elif evidence.get("rows"):
                parts.append(f"  {evidence['template']}: {evidence['rows']}")
            else:
                parts.append(f"  {evidence['template']}: no anomalies found")
        parts.append("")

    # Then the code
    parts.append(f"== SQL MODEL: {model_name} ==")
    # Add line numbers for reference
    numbered_lines = []
    for i, line in enumerate(model_sql.splitlines(), 1):
        numbered_lines.append(f"{i:3d} | {line}")
    parts.append("\n".join(numbered_lines))

    return "\n".join(parts)
