"""
graph.py — LangGraph workflow definition.

Wires all investigation nodes into a directed graph.
The graph follows the architecture from blueprint Section 9.2.

Flow:
    intake → context_collector → signal_extractor → classifier
    → router (conditional) → evidence_analyzer → [code_inspector]
    → lineage_tracer → incident_retriever → root_cause_reasoner
    → fix_generator → response_formatter

Day 6: Nodes 1-5 (intake through router)
Day 7: Nodes 6-12 (evidence through response formatter)
"""

import logging

from langgraph.graph import StateGraph, END

from agent.state import InvestigationState
from agent.nodes.intake import intake_node
from agent.nodes.context_collector import context_collector_node
from agent.nodes.signal_extractor import signal_extractor_node
from agent.nodes.classifier import classifier_node
from agent.nodes.router import route_investigation

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Build the complete investigation workflow graph."""

    graph = StateGraph(InvestigationState)

    # ── Add nodes ───────────────────────────────────────────
    graph.add_node("intake", intake_node)
    graph.add_node("context_collector", context_collector_node)
    graph.add_node("signal_extractor", signal_extractor_node)
    graph.add_node("classifier", classifier_node)

    # Placeholder nodes for Day 7 — currently pass through
    graph.add_node("evidence_analyzer", _placeholder_node("evidence_analyzer"))
    graph.add_node("code_inspector", _placeholder_node("code_inspector"))
    graph.add_node("lineage_tracer", _placeholder_node("lineage_tracer"))
    graph.add_node("incident_retriever", _placeholder_node("incident_retriever"))
    graph.add_node("root_cause_reasoner", _placeholder_node("root_cause_reasoner"))
    graph.add_node("fix_generator", _placeholder_node("fix_generator"))
    graph.add_node("response_formatter", _placeholder_node("response_formatter"))

    # ── Set entry point ─────────────────────────────────────
    graph.set_entry_point("intake")

    # ── Add edges (Node 1 → 2 → 3 → 4) ────────────────────
    graph.add_edge("intake", "context_collector")
    graph.add_edge("context_collector", "signal_extractor")
    graph.add_edge("signal_extractor", "classifier")

    # ── Conditional routing after classifier (Node 5) ───────
    graph.add_conditional_edges(
        "classifier",
        route_investigation,
        {
            "evidence_and_code": "evidence_analyzer",
            "evidence_only": "evidence_analyzer",
        },
    )

    # ── Evidence analyzer → conditional code inspection ─────
    graph.add_conditional_edges(
        "evidence_analyzer",
        _should_inspect_code,
        {
            "inspect_code": "code_inspector",
            "skip_code": "lineage_tracer",
        },
    )

    # ── Code inspector → lineage tracer ─────────────────────
    graph.add_edge("code_inspector", "lineage_tracer")

    # ── Lineage → retriever → reasoner → fix → format ──────
    graph.add_edge("lineage_tracer", "incident_retriever")
    graph.add_edge("incident_retriever", "root_cause_reasoner")
    graph.add_edge("root_cause_reasoner", "fix_generator")
    graph.add_edge("fix_generator", "response_formatter")

    # ── Response formatter → END ────────────────────────────
    graph.add_edge("response_formatter", END)

    return graph


def compile_graph():
    """Build and compile the graph for execution."""
    graph = build_graph()
    return graph.compile()


def _should_inspect_code(state: InvestigationState) -> str:
    """Determine whether to run code inspection after evidence collection."""
    failure_class = state.get("failure_class", "")
    has_code = bool(state.get("code_context"))

    code_classes = {"code_failure", "data_quality", "schema_drift", "silent_correctness"}

    if failure_class in code_classes and has_code:
        return "inspect_code"
    return "skip_code"


def _placeholder_node(name: str):
    """Create a placeholder node that logs and passes through.

    These will be replaced with real implementations on Day 7.
    """
    def node_fn(state: InvestigationState) -> dict:
        logger.info("[%s] Placeholder — will be implemented on Day 7", name.upper())
        return {}

    return node_fn
