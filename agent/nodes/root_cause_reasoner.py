"""
root_cause_reasoner.py — Node 10: Root Cause Reasoner

The most important LLM call. Sends all gathered evidence to GPT-4o
with explicit chain-of-thought instructions. The prompt presents
evidence in clearly labeled sections and instructs the LLM to
consider each piece, identify what it confirms and rules out,
evaluate competing hypotheses, and select the best-supported root cause.

"""

import json
import logging

from langchain_openai import ChatOpenAI

from agent.state import InvestigationState
from agent.prompts import reasoning
from agent.utils.config import MODELS, LLM_TEMPERATURE
from agent.utils.context_budget import get_output_budget

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

    try:
        llm = ChatOpenAI(
            model=MODELS["root_cause_reasoning"],
            temperature=LLM_TEMPERATURE,
            max_tokens=get_output_budget("root_cause_reasoning"),
        )

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

        response = llm.invoke([
            {"role": "system", "content": reasoning.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ])

        result = _parse_json(response.content)

        root_cause = result.get("root_cause", "Unable to determine root cause")
        confidence = result.get("confidence", 0.0)
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

    except Exception as e:
        logger.error("[REASONING] Root cause reasoning failed: %s", e)
        return {
            "root_cause": f"Analysis failed: {e}",
            "evidence_chain": [],
            "confidence": 0.0,
            "alternative_causes": [],
        }


def _parse_json(text: str) -> dict:
    """Parse JSON from LLM response."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())
