"""
response_formatter.py — Node 12: Response Formatter

Pure code, no LLM. Assembles the final structured incident report
from all state fields. Stores the completed investigation in the
incident table and generates an embedding for future retrieval.
"""

import json
import logging

from agent.state import InvestigationState
from agent.memory.incident_store import insert_incident
from agent.memory.embedding_service import (
    build_embedding_text,
    generate_embedding,
    store_incident_embedding,
)

logger = logging.getLogger(__name__)


def response_formatter_node(state: InvestigationState) -> dict:
    """Response Formatter — assembles and stores the final report.

    Reads: All state fields from previous nodes
    Writes: final_report
    """
    logger.info("[REPORT] Assembling final investigation report...")

    # ── Build the structured report (Appendix B format) ─────
    report = {
        "incident_id": state.get("incident_id", ""),
        "severity": state.get("severity", "error"),
        "failure_class": state.get("failure_class", "unknown"),
        "what_failed": _build_what_failed(state),
        "where_failed": {
            "dag_id": state.get("dag_id", ""),
            "task_id": state.get("task_id", ""),
            "model": state.get("dbt_model", ""),
            "table": state.get("target_objects", {}).get("table", ""),
            "column": state.get("target_objects", {}).get("column", ""),
        },
        "how_it_failed": _build_how_failed(state),
        "root_cause": state.get("root_cause", ""),
        "evidence_chain": state.get("evidence_chain", []),
        "confidence": state.get("confidence", 0.0),
        "alternative_causes_considered": state.get("alternative_causes", []),
        "fix": state.get("fix_plan", {}),
        "prevention": state.get("prevention_plan", []),
    }

    # ── Store in incident database ──────────────────────────
    try:
        incident_record = {
            "incident_id": report["incident_id"],
            "severity": report["severity"],
            "status": "resolved",
            "source": "agent",
            "pipeline_name": state.get("pipeline_name", ""),
            "dag_id": state.get("dag_id", ""),
            "task_id": state.get("task_id", ""),
            "run_id": state.get("run_id", ""),
            "dbt_model": state.get("dbt_model", ""),
            "target_table": state.get("target_objects", {}).get("table", ""),
            "target_column": state.get("target_objects", {}).get("column", ""),
            "failure_class": report["failure_class"],
            "issue_summary": report["what_failed"],
            "root_cause": report["root_cause"],
            "confidence": report["confidence"],
            "fix_summary": json.dumps(report["fix"]),
            "prevention_summary": json.dumps(report["prevention"]),
            "evidence_json": {
                "evidence_chain": report["evidence_chain"],
                "alternative_causes": report["alternative_causes_considered"],
                "database_evidence_count": len(state.get("database_evidence", [])),
                "code_findings_count": len(
                    state.get("code_findings", {}).get("findings", [])
                ),
                "similar_incidents_count": len(state.get("similar_incidents", [])),
            },
            "validated": False,
        }

        insert_incident(incident_record)

        # Generate and store embedding for future retrieval
        embedding_text = build_embedding_text(
            report["what_failed"],
            report["root_cause"],
        )
        embedding = generate_embedding(embedding_text)
        store_incident_embedding(report["incident_id"], embedding)

        logger.info(
            "[REPORT] Incident %s stored and embedded",
            report["incident_id"],
        )

    except Exception as e:
        logger.error("[REPORT] Failed to store incident: %s", e)

    # ── Log summary ─────────────────────────────────────────
    logger.info("[REPORT] Investigation complete.")
    logger.info("  Incident: %s", report["incident_id"])
    logger.info("  Class: %s", report["failure_class"])
    logger.info("  Confidence: %.2f", report["confidence"])
    logger.info("  Root cause: %s", report["root_cause"][:150])

    return {"final_report": report}


def _build_what_failed(state: InvestigationState) -> str:
    """Build a human-readable summary of what failed."""
    signals = state.get("extracted_signals", {})
    dbt_model = state.get("dbt_model", "")
    error_type = signals.get("error_type", "unknown")
    error_msg = signals.get("error_message", "")
    question = state.get("question", "")

    if question:
        return f"Investigation triggered by question: {question}"

    parts = []
    if dbt_model:
        parts.append(f"{dbt_model} model failed")
    if error_type and error_type != "unknown":
        parts.append(f"with {error_type}")
    if error_msg:
        parts.append(f"— {error_msg[:200]}")

    return " ".join(parts) if parts else "Pipeline failure detected"


def _build_how_failed(state: InvestigationState) -> str:
    code_findings = state.get("code_findings", {})
    primary_finding = code_findings.get("primary_finding", "")

    if primary_finding:
        return primary_finding

    signals = state.get("extracted_signals", {})
    error_msg = signals.get("error_message")
    if error_msg:
        return error_msg

    question = state.get("question")
    if question:
        return "Silent correctness issue — pipeline succeeded but data may be incorrect."

    return "Failure mechanism not determined"
