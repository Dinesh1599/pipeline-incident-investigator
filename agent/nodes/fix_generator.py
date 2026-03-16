"""
fix_generator.py — Node 11: Fix Generator

Sends the root cause, evidence chain, and code context to GPT-4o.
Generates immediate fix, preventive fix, and monitoring recommendation.
"""

import logging

from agent.state import InvestigationState
from agent.prompts import fix_generation
from agent.utils.config import MODELS
from agent.utils.context_budget import get_output_budget
from agent.utils.llm_caller import call_llm_json

logger = logging.getLogger(__name__)


def fix_generator_node(state: InvestigationState) -> dict:
    """Fix Generator — produces actionable recommendations.

    Reads: root_cause, evidence_chain, confidence, code_context,
           dbt_model, failure_class
    Writes: fix_plan, prevention_plan
    """
    root_cause = state.get("root_cause", "")
    evidence_chain = state.get("evidence_chain", [])
    confidence = state.get("confidence", 0.0)
    code_context = state.get("code_context", "")
    dbt_model = state.get("dbt_model", "unknown")
    failure_class = state.get("failure_class", "unknown")

    if not root_cause:
        logger.info("[FIX] No root cause available, skipping fix generation")
        return {"fix_plan": {}, "prevention_plan": []}

    logger.info("[FIX] Generating fix recommendations...")

    user_msg = fix_generation.build_user_message(
        root_cause=root_cause,
        evidence_chain=evidence_chain,
        confidence=confidence,
        code_context=code_context,
        model_name=dbt_model,
        failure_class=failure_class,
    )

    result = call_llm_json(
        model=MODELS["fix_generation"],
        system_prompt=fix_generation.SYSTEM_PROMPT,
        user_message=user_msg,
        max_tokens=get_output_budget("fix_generation"),
        node_name="FIX",
    )

    if result:
        fix_plan = result.get("fix", {})
        prevention_plan = result.get("prevention", [])

        logger.info("[FIX] Immediate: %s", fix_plan.get("immediate", "")[:100])
        logger.info("[FIX] Preventive: %s", fix_plan.get("preventive", "")[:100])
        logger.info("[FIX] Monitoring: %s", fix_plan.get("monitoring", "")[:100])

        return {
            "fix_plan": fix_plan,
            "prevention_plan": prevention_plan,
        }
    else:
        logger.error("[FIX] Fix generation returned no results")
        return {"fix_plan": {}, "prevention_plan": []}