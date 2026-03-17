"""
fix_generation.py — Fix and Prevention Generation prompt template.

Model: GPT-4o
Token budget: 2000 input, 600 output
Task type: Recommendation generation

Includes examples of good vs bad recommendations. Pushes for
specificity by showing what specificity looks like.
"""

SYSTEM_PROMPT = """You are a senior data engineer recommending fixes for a data pipeline failure. You have been given the root cause analysis and supporting evidence.

Generate three categories of recommendations:
1. Immediate fix — what to change RIGHT NOW to resolve this specific failure
2. Preventive fix — what test or guardrail to ADD so this class of failure is caught earlier next time
3. Monitoring recommendation — what alert to SET UP so the team is notified before it becomes a failure

Each recommendation must reference SPECIFIC objects (tables, columns, models) and SPECIFIC actions. Generic advice is not acceptable.

## Good vs Bad Examples

BAD immediate fix: "Check your data"
GOOD immediate fix: "Add WHERE customer_id IS NOT NULL filter to fct_sales.sql before the JOIN on line 12"

BAD preventive fix: "Add data validation"
GOOD preventive fix: "Add a not_null dbt test on bronze.sales.customer_id in models/silver/schema.yml"

BAD monitoring: "Monitor the pipeline"
GOOD monitoring: "Add an alert that triggers when null count in bronze.sales.customer_id exceeds 1% of total rows"

Respond with ONLY valid JSON matching the schema. No explanation, no markdown.

{
  "fix": {
    "immediate": "string — specific change to make right now",
    "preventive": "string — specific test or guardrail to add",
    "monitoring": "string — specific alert to set up"
  },
  "prevention": [
    "string — additional preventive measures beyond the primary fix, if any"
  ],
  "fix_confidence": "float 0.0-1.0 — confidence that the immediate fix will resolve the issue",
  "requires_manual_review": "boolean — whether a human should review before applying"
}"""


def build_user_message(
    root_cause: str,
    evidence_chain: list[str],
    confidence: float,
    code_context: str,
    model_name: str,
    failure_class: str,
) -> str:
    """Build the user message for fix generation.

    Args:
        root_cause: The determined root cause from the Reasoner.
        evidence_chain: List of supporting evidence from the Reasoner.
        confidence: Confidence score from the Reasoner.
        code_context: The SQL model code (for referencing specific lines).
        model_name: The dbt model name.
        failure_class: The classified failure type.
    """
    parts = []

    parts.append("== ROOT CAUSE ==")
    parts.append(root_cause)
    parts.append(f"Confidence: {confidence}")
    parts.append(f"Failure class: {failure_class}")
    parts.append("")

    parts.append("== EVIDENCE CHAIN ==")
    for i, evidence in enumerate(evidence_chain, 1):
        parts.append(f"  {i}. {evidence}")
    parts.append("")

    if code_context:
        parts.append(f"== MODEL CODE: {model_name} ==")
        numbered_lines = []
        for i, line in enumerate(code_context.splitlines(), 1):
            numbered_lines.append(f"{i:3d} | {line}")
        parts.append("\n".join(numbered_lines))

    return "\n".join(parts)
