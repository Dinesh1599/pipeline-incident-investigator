"""
root_cause_reasoner.py — Node 10: Root Cause Reasoner

The most important LLM call. Sends all gathered evidence to GPT-4o
with explicit chain-of-thought instructions.
"""

import logging

from agent.state import InvestigationState
from agent.prompts import reasoning
from agent.utils.config import MODELS
from agent.utils.context_budget import get_output_budget
from agent.utils.llm_caller import call_llm_json

logger = logging.getLogger(__name__)


def root_cause_reasoner_node(state: InvestigationState) -> dict:
    """Root Cause Reasoner — synthesizes all evidence into a diagnosis.

    Reads: extracted_signals, failure_class, classification_confidence,
           database_evidence, upstream_evidence, code_findings,
           lineage_trace, similar_incidents, logs_available,
           db_evidence_available
    Writes: root_cause, evidence_chain, confidence, alternative_causes
    """
    signals = state.get("extracted_signals", {})
    failure_class = state.get("failure_class", "unknown")
    classification = {
        "primary_class": failure_class,
        "secondary_class": state.get("secondary_class"),
        "confidence": state.get("classification_confidence", 0.0),
    }

    # Combine direct and upstream evidence
    db_evidence = state.get("database_evidence", [])
    upstream_evidence = state.get("upstream_evidence", [])
    all_evidence = db_evidence + upstream_evidence

    code_findings = state.get("code_findings", {})
    lineage = state.get("lineage_trace", state.get("lineage_context", {}))
    similar_incidents = state.get("similar_incidents", [])
    logs_available = state.get("logs_available", False)
    db_available = state.get("db_evidence_available", False)

    logger.info("[REASONING] Synthesizing evidence for root cause analysis...")
    logger.info(
        "  Evidence: %d db checks, %d code findings, %d similar incidents",
        len(all_evidence),
        len(code_findings.get("findings", [])),
        len(similar_incidents),
    )

    # ── Apply confidence caps based on evidence availability ──
    confidence_cap = 1.0
    if not logs_available:
        confidence_cap = min(confidence_cap, 0.7)
        logger.info("  Logs unavailable — confidence capped at 0.7")
    if not db_available:
        confidence_cap = min(confidence_cap, 0.5)
        logger.info("  DB evidence unavailable — confidence capped at 0.5")

    user_msg = reasoning.build_user_message(
        failure_signals=signals,
        classification=classification,
        database_evidence=all_evidence,
        code_findings=code_findings,
        lineage_context=lineage,
        similar_incidents=similar_incidents,
        logs_available=logs_available,
        db_evidence_available=db_available,
    )

    result = call_llm_json(
        model=MODELS["root_cause_reasoning"],
        system_prompt=reasoning.SYSTEM_PROMPT,
        user_message=user_msg,
        max_tokens=get_output_budget("root_cause_reasoning"),
        node_name="REASONING",
    )

    if result:
        root_cause = result.get("root_cause", "Unable to determine root cause")
        confidence = min(result.get("confidence", 0.0), confidence_cap)
        evidence_chain = result.get("evidence_chain", [])
        alternatives = result.get("alternative_causes_considered", [])

        logger.info("[REASONING] Root cause (confidence: %.2f):", confidence)
        logger.info("  %s", root_cause[:150])
        logger.info("  Evidence chain: %d items", len(evidence_chain))
        logger.info("  Alternatives considered: %d", len(alternatives))

        return {
            "root_cause": root_cause,
            "evidence_chain": evidence_chain,
            "confidence": confidence,
            "alternative_causes": alternatives,
        }
    else:
        logger.error("[REASONING] Root cause reasoning returned no results")
        return {
            "root_cause": "Analysis failed — LLM returned no usable response",
            "evidence_chain": [],
            "confidence": 0.0,
            "alternative_causes": [],
        }