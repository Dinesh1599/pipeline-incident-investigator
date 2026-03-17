"""
code_inspector.py — Node 7: Code Inspector

Sends the dbt model SQL plus failure context and evidence results
to GPT-4o. Identifies code constructs causing or contributing to
the failure.

"""

import json
import logging

from agent.state import InvestigationState
from agent.prompts import code_inspection
from agent.utils.config import MODELS
from agent.utils.context_budget import prepare_context, get_output_budget
from agent.utils.llm_caller import call_llm_json

logger = logging.getLogger(__name__)


def code_inspector_node(state: InvestigationState) -> dict:
    """Code Inspector — targeted code review for the failing model.

    Reads: extracted_signals, failure_class, classification_confidence,
           database_evidence, code_context, dbt_model
    Writes: code_findings
    """
    code_context = state.get("code_context", "")
    dbt_model = state.get("dbt_model", "unknown")
    signals = state.get("extracted_signals", {})
    failure_class = state.get("failure_class", "unknown")
    classification = {
        "primary_class": failure_class,
        "confidence": state.get("classification_confidence", 0.0),
        "reasoning": "",
    }
    evidence = state.get("database_evidence", [])

    if not code_context:
        logger.info("[CODE] No model SQL available, skipping code inspection")
        return {"code_findings": {}}

    logger.info("[CODE] Inspecting %s.sql (%d lines)...", dbt_model, len(code_context.splitlines()))

    user_msg = code_inspection.build_user_message(
        failure_context=signals,
        classification=classification,
        evidence_results=evidence,
        model_sql=code_context,
        model_name=dbt_model,
    )

    result = call_llm_json(
        model=MODELS["code_inspection"],
        system_prompt=code_inspection.SYSTEM_PROMPT,
        user_message=user_msg,
        max_tokens=get_output_budget("code_inspection"),
        node_name="CODE",
    )

    if result:
        findings_count = len(result.get("findings", []))
        logger.info("[CODE] Found %d issues in %s.sql", findings_count, dbt_model)
        for f in result.get("findings", []):
            logger.info(
                "  [%s] %s: %s",
                f.get("severity", "?"),
                f.get("location", "?"),
                f.get("issue", "")[:80],
            )
    else:
        logger.warning("[CODE] Code inspection returned no results")

    return {"code_findings": result}