"""
code_inspector.py — Node 7: Code Inspector

Sends the dbt model SQL plus failure context and evidence results
to GPT-4o. Identifies code constructs causing or contributing to
the failure.

"""

import json
import logging

from langchain_openai import ChatOpenAI

from agent.state import InvestigationState
from agent.prompts import code_inspection
from agent.utils.config import MODELS, LLM_TEMPERATURE
from agent.utils.context_budget import prepare_context, get_output_budget

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

    try:
        # Budget context
        prepared = prepare_context("code_inspection", {
            "signals": json.dumps(signals, default=str),
            "evidence": json.dumps(evidence, default=str),
            "code": code_context,
        })

        llm = ChatOpenAI(
            model=MODELS["code_inspection"],
            temperature=LLM_TEMPERATURE,
            max_tokens=get_output_budget("code_inspection"),
        )

        user_msg = code_inspection.build_user_message(
            failure_context=signals,
            classification=classification,
            evidence_results=evidence,
            model_sql=code_context,
            model_name=dbt_model,
        )

        response = llm.invoke([
            {"role": "system", "content": code_inspection.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ])

        result = _parse_json(response.content)

        findings_count = len(result.get("findings", []))
        logger.info("[CODE] Found %d issues in %s.sql", findings_count, dbt_model)
        for f in result.get("findings", []):
            logger.info(
                "  [%s] %s: %s",
                f.get("severity", "?"),
                f.get("location", "?"),
                f.get("issue", "")[:80],
            )

        return {"code_findings": result}

    except Exception as e:
        logger.error("[CODE] Code inspection failed: %s", e)
        return {"code_findings": {}}


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
