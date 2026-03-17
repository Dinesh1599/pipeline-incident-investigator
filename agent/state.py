"""
state.py — Investigation state model.

The graph state is a typed dictionary that accumulates evidence
throughout the investigation. All nodes read from and write to
this shared state.
"""

from typing import Optional
from typing_extensions import TypedDict


class InvestigationState(TypedDict, total=False):
    """Shared state for the LangGraph investigation workflow.

    All fields are optional (total=False) because they are
    populated incrementally by different nodes.
    """

    # ── Intake (Node 1) ─────────────────────────────────────
    incident_id: str
    question: Optional[str]           # Free-form user question (if manual trigger)
    dag_id: str
    task_id: str
    run_id: str
    pipeline_name: str
    severity: str
    error_message: Optional[str]      # From trigger payload
    dbt_model: Optional[str]          # Resolved from task_id

    # ── Context Collector (Node 2) ──────────────────────────
    logs_raw: str
    logs_available: bool
    pipeline_metadata: dict           # Task instance + DAG run info
    dbt_manifest_entry: dict          # Model entry from manifest.json
    dbt_run_result: dict              # Run result for the model
    database_metadata: dict           # INFORMATION_SCHEMA for target tables
    code_context: str                 # Raw SQL of the dbt model
    lineage_context: dict             # Upstream/downstream from manifest

    # ── Signal Extractor (Node 3) ───────────────────────────
    extracted_signals: dict           # LLM + regex extraction output
    target_objects: dict              # Schema, table, column to investigate

    # ── Classifier (Node 4) ─────────────────────────────────
    failure_class: str                # Primary classification
    secondary_class: Optional[str]    # Secondary if ambiguous
    classification_confidence: float
    investigation_priorities: list[str]

    # ── Database Evidence Analyzer (Node 6) ─────────────────
    database_evidence: list[dict]     # Results from SQL evidence checks
    upstream_evidence: list[dict]     # Results from upstream table checks
    db_evidence_available: bool

    # ── Code Inspector (Node 7) ─────────────────────────────
    code_findings: dict               # Structured findings from code review

    # ── Lineage Tracer (Node 8) ─────────────────────────────
    lineage_trace: dict               # Full lineage with upstream/downstream

    # ── Incident Retriever (Node 9) ─────────────────────────
    similar_incidents: list[dict]     # Top-k similar past incidents

    # ── Root Cause Reasoner (Node 10) ───────────────────────
    root_cause: str
    evidence_chain: list[str]
    confidence: float
    alternative_causes: list[dict]

    # ── Fix Generator (Node 11) ─────────────────────────────
    fix_plan: dict                    # Immediate, preventive, monitoring
    prevention_plan: list[str]

    # ── Response Formatter (Node 12) ────────────────────────
    final_report: dict                # Complete structured incident report
