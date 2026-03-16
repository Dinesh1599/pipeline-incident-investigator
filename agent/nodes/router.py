"""
router.py — Node 5: Conditional Router

A pure code node (no LLM). Reads the failure_class and
investigation_priorities, returns the next node(s) to execute.

Blueprint reference: Section 9.2 (Node 5)

Routes:
    data_quality       → evidence_analyzer
    schema_drift       → evidence_analyzer
    code_failure       → evidence_analyzer + code_inspector
    dependency         → evidence_analyzer
    silent_correctness → evidence_analyzer
    resource           → evidence_analyzer
    access             → evidence_analyzer
    unknown            → evidence_analyzer

When classification is ambiguous (secondary_class within 0.15
of primary), both paths are triggered.
"""

import logging

from agent.state import InvestigationState

logger = logging.getLogger(__name__)

# Failure classes that should also run code inspection
CODE_INSPECTION_CLASSES = {"code_failure", "data_quality", "schema_drift", "silent_correctness"}


def route_investigation(state: InvestigationState) -> str:
    """Determine the next node based on failure classification.

    Returns a string key used by LangGraph's conditional edge
    to route to the appropriate evidence collection path.

    Possible return values:
        'evidence_and_code' — run evidence analyzer then code inspector
        'evidence_only'     — run evidence analyzer only
    """
    failure_class = state.get("failure_class", "unknown")
    secondary_class = state.get("secondary_class")
    confidence = state.get("classification_confidence", 0.0)

    # Determine if code inspection is needed
    needs_code = failure_class in CODE_INSPECTION_CLASSES

    # If secondary class is close and also needs code inspection
    if secondary_class and secondary_class in CODE_INSPECTION_CLASSES:
        needs_code = True

    # If we have model SQL available
    has_code = bool(state.get("code_context"))

    if needs_code and has_code:
        route = "evidence_and_code"
    else:
        route = "evidence_only"

    logger.info(
        "[ROUTER] Class=%s, secondary=%s, confidence=%.2f → %s",
        failure_class,
        secondary_class,
        confidence,
        route,
    )

    return route
