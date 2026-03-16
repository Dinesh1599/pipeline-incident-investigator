"""
classifier.py — Node 4: Classifier

Sends extracted signals plus pipeline metadata to GPT-4o-mini
with a classification prompt. Outputs primary class, optional
secondary class, confidence, reasoning, and investigation priorities.

Blueprint reference: Section 9.2 (Node 4), Section 10.2
"""

import json
import logging

from langchain_openai import ChatOpenAI

from agent.state import InvestigationState
from agent.prompts import classification
from agent.utils.config import MODELS, LLM_TEMPERATURE
from agent.utils.context_budget import get_output_budget

logger = logging.getLogger(__name__)


def classifier_node(state: InvestigationState) -> dict:
    """Classifier — categorizes the failure type.

    Reads: extracted_signals, pipeline_metadata, dbt_model,
           dag_id, task_id, question
    Writes: failure_class, secondary_class, classification_confidence,
            investigation_priorities
    """
    extracted_signals = state.get("extracted_signals", {})
    pipeline_metadata = state.get("pipeline_metadata", {})
    dbt_model = state.get("dbt_model")
    question = state.get("question")

    # Build metadata summary for classification
    metadata_summary = {
        "dag_id": state.get("dag_id", ""),
        "task_id": state.get("task_id", ""),
        "model_name": dbt_model or "unknown",
    }

    # Add model description from manifest if available
    manifest_entry = state.get("dbt_manifest_entry", {})
    if manifest_entry.get("description"):
        metadata_summary["model_description"] = manifest_entry["description"]

    logger.info("[CLASSIFY] Calling GPT-4o-mini for classification...")

    try:
        llm = ChatOpenAI(
            model=MODELS["classification"],
            temperature=LLM_TEMPERATURE,
            max_tokens=get_output_budget("classification"),
        )

        user_msg = classification.build_user_message(
            extracted_signals=extracted_signals,
            pipeline_metadata=metadata_summary,
            question=question,
        )

        response = llm.invoke([
            {"role": "system", "content": classification.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ])

        result = _parse_classification(response.content)

        logger.info(
            "[CLASSIFY] Classification: %s (confidence: %.2f)",
            result.get("primary_class", "unknown"),
            result.get("confidence", 0.0),
        )

        return {
            "failure_class": result.get("primary_class", "unknown"),
            "secondary_class": result.get("secondary_class"),
            "classification_confidence": result.get("confidence", 0.0),
            "investigation_priorities": result.get("investigation_priorities", []),
        }

    except Exception as e:
        logger.error("[CLASSIFY] Classification failed: %s", e)
        return _fallback_classification(extracted_signals)


def _parse_classification(response_text: str) -> dict:
    """Parse classification JSON from LLM response."""
    cleaned = response_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError:
        logger.warning("[CLASSIFY] Malformed JSON, attempting extraction...")
        # Try to find JSON in the response
        import re
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise


def _fallback_classification(signals: dict) -> dict:
    """Rule-based fallback when LLM classification fails.

    Maps common error types to failure classes deterministically.
    """
    error_type = signals.get("error_type", "")

    fallback_map = {
        "not_null_violation": "data_quality",
        "unique_violation": "data_quality",
        "type_cast_failure": "schema_drift",
        "relation_not_found": "code_failure",
        "column_not_found": "code_failure",
        "dbt_compile_error": "code_failure",
        "dbt_database_error": "data_quality",
        "permission_denied": "access",
        "timeout": "resource",
        "oom": "resource",
    }

    failure_class = fallback_map.get(error_type, "unknown")

    priority_map = {
        "data_quality": ["null_check", "duplicate_check", "row_count"],
        "schema_drift": ["column_presence", "invalid_cast_check"],
        "code_failure": ["code_inspection", "lineage_check"],
        "access": ["permission_check"],
        "resource": ["row_count"],
        "unknown": ["null_check", "row_count", "column_presence"],
    }

    logger.warning(
        "[CLASSIFY] Using fallback classification: %s (from error_type: %s)",
        failure_class,
        error_type,
    )

    return {
        "failure_class": failure_class,
        "secondary_class": None,
        "classification_confidence": 0.5,
        "investigation_priorities": priority_map.get(failure_class, []),
    }
