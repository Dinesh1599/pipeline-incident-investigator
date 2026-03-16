"""
evidence_analyzer.py — Node 6: Database Evidence Analyzer

Pure code, no LLM. Selects parameterized SQL query templates based
on the failure class and target objects. Executes queries against
Postgres. Formats results as structured evidence.

Never generates SQL dynamically from LLM output for safety.


"""

import logging

from agent.state import InvestigationState
from agent.connectors.postgres_connector import PostgresConnector
from agent.evidence.query_templates import run_checks_for_class, run_upstream_checks

logger = logging.getLogger(__name__)


def evidence_analyzer_node(state: InvestigationState) -> dict:
    """Database Evidence Analyzer — runs targeted SQL checks.

    Reads: failure_class, target_objects, lineage_context,
           extracted_signals, investigation_priorities
    Writes: database_evidence, upstream_evidence, db_evidence_available
    """
    failure_class = state.get("failure_class", "unknown")
    target_objects = state.get("target_objects", {})
    lineage = state.get("lineage_context", {})
    signals = state.get("extracted_signals", {})

    logger.info("[EVIDENCE] Running checks for class: %s", failure_class)

    try:
        pg = PostgresConnector()

        # ── Build target from lineage if not set by signals ──
        if not target_objects.get("table"):
            # Fall back to upstream sources from lineage
            sources = lineage.get("upstream_sources", [])
            if sources:
                target_objects["schema"] = sources[0].get("schema", "bronze")
                target_objects["table"] = sources[0].get("table_name", "")

        # Get column from signals if available
        objects_ref = signals.get("objects_referenced", {})
        if not target_objects.get("column") and objects_ref.get("columns"):
            target_objects["column"] = objects_ref["columns"][0]

        # ── Run checks for the primary failure class ────────
        evidence = []
        if target_objects.get("table"):
            evidence = run_checks_for_class(pg, failure_class, target_objects)
            logger.info(
                "[EVIDENCE] Ran %d checks on %s.%s",
                len(evidence),
                target_objects.get("schema", "?"),
                target_objects.get("table", "?"),
            )
        else:
            logger.warning("[EVIDENCE] No target table identified, skipping checks")

        # ── Run upstream checks ─────────────────────────────
        upstream_evidence = []
        upstream_sources = lineage.get("upstream_sources", [])
        upstream_models = lineage.get("upstream_models", [])

        # Build upstream table list
        upstream_tables = []
        for source in upstream_sources:
            upstream_tables.append({
                "schema": source.get("schema", "bronze"),
                "table_name": source.get("table_name"),
            })
        for model_name in upstream_models:
            # Determine schema from model name convention
            if model_name.startswith("silver_"):
                upstream_tables.append({"schema": "silver", "table_name": model_name})
            else:
                upstream_tables.append({"schema": "public", "table_name": model_name})

        if upstream_tables:
            column = target_objects.get("column")
            upstream_evidence = run_upstream_checks(pg, upstream_tables, column=column)
            logger.info(
                "[EVIDENCE] Ran %d upstream checks on %d tables",
                len(upstream_evidence),
                len(upstream_tables),
            )

        # ── Log summary ─────────────────────────────────────
        for e in evidence:
            if e.get("error"):
                logger.info("  [%s] ERROR: %s", e["template"], e["error"])
            elif e.get("rows"):
                logger.info("  [%s] %s", e["template"], e["rows"])
            else:
                logger.info("  [%s] no anomalies", e["template"])

        return {
            "database_evidence": evidence,
            "upstream_evidence": upstream_evidence,
            "db_evidence_available": bool(evidence) or bool(upstream_evidence),
        }

    except Exception as e:
        logger.error("[EVIDENCE] Database evidence collection failed: %s", e)
        return {
            "database_evidence": [],
            "upstream_evidence": [],
            "db_evidence_available": False,
        }
