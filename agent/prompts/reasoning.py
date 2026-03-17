"""
reasoning.py — Root Cause Reasoning prompt template.

Model: GPT-4o
Token budget: 4000 input, 1000 output
Task type: Multi-evidence synthesis and reasoning

Blueprint reference: Section 10.4

This is the most important LLM call. The prompt instructs explicit
step-by-step reasoning: consider each piece of evidence, identify
what it confirms and rules out, enumerate possible causes, evaluate
which is best supported, and rate confidence.

The alternative_causes_considered field forces the LLM to think about
competing explanations, significantly improving reasoning quality.
"""

SYSTEM_PROMPT = """You are a senior data engineer conducting root cause analysis on a data pipeline failure. You have been given evidence from multiple sources. Your job is to synthesize this evidence into a definitive root cause diagnosis.

You MUST reason step by step:
1. Consider each piece of evidence individually — what does it confirm? What does it rule out?
2. Enumerate all possible causes that could explain the evidence
3. Evaluate which cause is best supported by the combined evidence
4. Assign a confidence score based on evidence strength
5. Explain why you ruled out alternative causes

Respond with ONLY valid JSON matching the schema. No explanation, no markdown.

{
  "root_cause": "string — specific, evidence-backed root cause statement",
  "evidence_chain": [
    "string — each supporting fact that leads to the conclusion, in logical order"
  ],
  "confidence": "float 0.0-1.0 — confidence in this diagnosis",
  "alternative_causes_considered": [
    {
      "cause": "string — alternative cause that was considered",
      "ruled_out_by": "string — which evidence ruled this out"
    }
  ]
}

## Confidence Guidelines

0.80 - 1.00 (High): Multiple evidence sources corroborate the same root cause. State root cause directly.
0.50 - 0.79 (Medium): Some evidence found but not fully conclusive. State best assessment, flag uncertainty.
0.00 - 0.49 (Low): Insufficient evidence. Report what was found, suggest manual investigation.

## Important Rules

- Every claim in root_cause must be supported by at least one item in evidence_chain
- If evidence is contradictory, acknowledge it and explain which evidence you weigh more heavily
- If logs were unavailable, note this and cap confidence at 0.7
- If database evidence was unavailable, note this and cap confidence at 0.5
- Do NOT guess or fill gaps with assumptions. If you don't know, say so.
- When the evidence points to a data issue but the CAUSE of the data issue isn't clear, say so rather than guessing

## Specificity Requirements

Your root_cause and evidence_chain MUST reference specific objects:
- Always name the exact schema and table (e.g., "bronze.sales", NOT "source data" or "upstream table")
- Always name the exact column (e.g., "customer_id", "order_date", NOT "the key column" or "the date field")
- Always include the specific values or counts from evidence (e.g., "0 rows for order_date = 2026-03-04", NOT "no data for that date")
- When tracing across layers, state each layer explicitly (e.g., "bronze.sales has 0 rows → silver.silver_sales has 0 rows → gold.fct_sales has 0 rows")

## Multi-Layer Investigation

When evidence includes checks across multiple pipeline layers (bronze, silver, gold), determine WHERE the issue originates:
- If the issue exists at bronze level: the root cause is in source data or ingestion
- If bronze is clean but silver has the issue: the root cause is in the transformation (dbt model)
- If bronze and silver are clean but gold has the issue: the root cause is in the aggregation or join logic
- Always trace from the LOWEST layer upward — the first layer showing the issue is where the root cause lives
- Do NOT blame transformation code (GROUP BY, JOIN, WHERE) for data that simply doesn't exist in the source

## Silent Correctness Investigations

When the failure class is silent_correctness and the investigation was triggered by a user question:
- The pipeline SUCCEEDED — there is no error in the code. The code ran correctly.
- Focus on what DATA is missing or wrong, not what CODE might be wrong
- partition_check showing 0 rows at the bronze layer means the source data was never delivered
- partition_check showing 0 rows at silver but not bronze means the transformation filtered it out
- Do NOT blame SQL constructs (GROUP BY, JOIN) for missing source data — they cannot create data that doesn't exist"""


def build_user_message(
    failure_signals: dict,
    classification: dict,
    database_evidence: list[dict],
    code_findings: dict,
    lineage_context: dict,
    similar_incidents: list[dict],
    logs_available: bool = True,
    db_evidence_available: bool = True,
) -> str:
    """Build the user message for root cause reasoning.

    All evidence is presented in clearly labeled sections so the LLM
    can reference specific evidence in its reasoning.
    """
    parts = []

    # Availability flags
    if not logs_available:
        parts.append("⚠ LOGS WERE UNAVAILABLE — do not infer log-based evidence. Cap confidence at 0.7.")
        parts.append("")
    if not db_evidence_available:
        parts.append("⚠ DATABASE EVIDENCE WAS UNAVAILABLE — diagnosis without DB evidence is limited. Cap confidence at 0.5.")
        parts.append("")

    # Section 1: Failure signals
    parts.append("== FAILURE SIGNALS ==")
    if failure_signals:
        for key, value in failure_signals.items():
            if key not in ("regex_matches", "parsed_question") and value:
                parts.append(f"  {key}: {value}")
    else:
        parts.append("  No signals extracted")
    parts.append("")

    # Section 2: Classification
    parts.append("== CLASSIFICATION ==")
    if classification:
        parts.append(f"  Primary class: {classification.get('primary_class', 'unknown')}")
        if classification.get('secondary_class'):
            parts.append(f"  Secondary class: {classification['secondary_class']}")
        parts.append(f"  Confidence: {classification.get('confidence', 'unknown')}")
    parts.append("")

    # Section 3: Database evidence
    parts.append("== DATABASE EVIDENCE ==")
    if database_evidence:
        # Group by layer/context for clarity
        by_context = {}
        for evidence in database_evidence:
            ctx = evidence.get("context", "direct")
            if ctx not in by_context:
                by_context[ctx] = []
            by_context[ctx].append(evidence)

        for ctx, items in by_context.items():
            parts.append(f"  --- {ctx} ---")
            for evidence in items:
                template = evidence.get("template", "unknown")
                if evidence.get("error"):
                    parts.append(f"    {template}: QUERY FAILED — {evidence['error'][:100]}")
                elif evidence.get("rows"):
                    parts.append(f"    {template}: {evidence['rows']}")
                else:
                    parts.append(f"    {template}: no anomalies found (this is evidence too)")
    else:
        parts.append("  No database evidence collected")
    parts.append("")

    # Section 4: Code inspection findings
    parts.append("== CODE INSPECTION ==")
    if code_findings and code_findings.get("findings"):
        for finding in code_findings["findings"]:
            parts.append(f"  [{finding.get('severity', '?')}] {finding.get('location', '?')}: {finding.get('issue', '')}")
            parts.append(f"    Relevance: {finding.get('relevance', '')}")
        if code_findings.get("primary_finding"):
            parts.append(f"  Primary finding: {code_findings['primary_finding']}")
    else:
        parts.append("  No code findings")
    parts.append("")

    # Section 5: Lineage context
    parts.append("== LINEAGE ==")
    if lineage_context:
        parts.append(f"  Model: {lineage_context.get('model', 'unknown')}")
        if lineage_context.get("dependency_chain"):
            parts.append(f"  Chain: {lineage_context['dependency_chain']}")
        else:
            parts.append(f"  Upstream models: {lineage_context.get('upstream_models', [])}")
            parts.append(f"  Upstream sources: {lineage_context.get('upstream_sources', [])}")
            parts.append(f"  Downstream affected: {lineage_context.get('downstream_models', [])}")
    else:
        parts.append("  No lineage context available")
    parts.append("")

    # Section 6: Similar past incidents (conditional)
    if similar_incidents:
        parts.append("== SIMILAR PAST INCIDENTS ==")
        for incident in similar_incidents:
            parts.append(f"  {incident.get('incident_id', '?')} (similarity: {incident.get('similarity_score', '?')})")
            parts.append(f"    Summary: {incident.get('summary', '')[:200]}")
            parts.append(f"    Root cause: {incident.get('root_cause', '')[:200]}")
            parts.append(f"    Fix applied: {incident.get('fix_applied', '')[:200]}")
            parts.append("")

    return "\n".join(parts)