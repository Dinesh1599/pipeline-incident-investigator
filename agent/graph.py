"""
graph.py — LangGraph workflow definition.

Wires all 12 investigation nodes into a directed graph.

Flow:
    intake → context_collector → signal_extractor → classifier
    → router (conditional) → evidence_analyzer → [code_inspector]
    → lineage_tracer → incident_retriever → root_cause_reasoner
    → fix_generator → response_formatter → END


"""

import logging

from langgraph.graph import StateGraph, END

from agent.state import InvestigationState
from agent.nodes.intake import intake_node
from agent.nodes.context_collector import context_collector_node
from agent.nodes.signal_extractor import signal_extractor_node
from agent.nodes.classifier import classifier_node
from agent.nodes.router import route_investigation
from agent.nodes.evidence_analyzer import evidence_analyzer_node
from agent.nodes.code_inspector import code_inspector_node
from agent.nodes.lineage_tracer import lineage_tracer_node
from agent.nodes.incident_retriever import incident_retriever_node
from agent.nodes.root_cause_reasoner import root_cause_reasoner_node
from agent.nodes.fix_generator import fix_generator_node
from agent.nodes.response_formatter import response_formatter_node

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Build the complete investigation workflow graph."""

    graph = StateGraph(InvestigationState)

    # ── Add nodes ───────────────────────────────────────────
    graph.add_node("intake", intake_node)
    graph.add_node("context_collector", context_collector_node)
    graph.add_node("signal_extractor", signal_extractor_node)
    graph.add_node("classifier", classifier_node)
    graph.add_node("evidence_analyzer", evidence_analyzer_node)
    graph.add_node("code_inspector", code_inspector_node)
    graph.add_node("lineage_tracer", lineage_tracer_node)
    graph.add_node("incident_retriever", incident_retriever_node)
    graph.add_node("root_cause_reasoner", root_cause_reasoner_node)
    graph.add_node("fix_generator", fix_generator_node)
    graph.add_node("response_formatter", response_formatter_node)

    # ── Set entry point ─────────────────────────────────────
    graph.set_entry_point("intake")

    # ── Edges: Node 1 → 2 → 3 → 4 ─────────────────────────
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