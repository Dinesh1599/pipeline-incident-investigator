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
- When the evidence points to a data issue but the CAUSE of the data issue isn't clear, say so rather than guessing"""


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

    Args:
        failure_signals: Output from Signal Extractor.
        classification: Output from Classifier.
        database_evidence: Results from Database Evidence Analyzer.
        code_findings: Output from Code Inspector.
        lineage_context: Output from Lineage Tracer.
        similar_incidents: Output from Incident Retriever.
        logs_available: Whether logs were successfully collected.
        db_evidence_available: Whether database evidence was collected.
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
            if key != "regex_matches" and value:
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
        parts.append(f"  Reasoning: {classification.get('reasoning', '')}")
    parts.append("")

    # Section 3: Database evidence
    parts.append("== DATABASE EVIDENCE ==")
    if database_evidence:
        for evidence in database_evidence:
            template = evidence.get("template", "unknown")
            context = evidence.get("context", "")
            prefix = f"  [{context}] " if context else "  "

            if evidence.get("error"):
                parts.append(f"{prefix}{template}: QUERY FAILED — {evidence['error']}")
            elif evidence.get("rows"):
                parts.append(f"{prefix}{template}: {evidence['rows']}")
            else:
                parts.append(f"{prefix}{template}: no anomalies found (this is evidence too)")
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
