"""
evidence_analyzer.py — Node 6: Database Evidence Analyzer

Pure code, no LLM. Selects parameterized SQL query templates based
on the failure class and target objects. Executes queries against
Postgres. Formats results as structured evidence.

For question-based investigations, runs checks across all pipeline
layers (bronze → silver → gold) to determine where the issue
originates.

Never generates SQL dynamically from LLM output for safety.
"""

import logging

from agent.state import InvestigationState
from agent.connectors.postgres_connector import PostgresConnector
from agent.evidence.query_templates import (
    run_checks_for_class,
    run_upstream_checks,
    run_evidence_check,
)

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

        # ── Redirect dbt temp tables to upstream ────────────
        table = target_objects.get("table", "")
        if table.endswith("__dbt_tmp"):
            logger.info(
                "[EVIDENCE] Target %s is a dbt temp table, redirecting to upstream sources",
                table,
            )
            sources = lineage.get("upstream_sources", [])
            models = lineage.get("upstream_models", [])
            if sources:
                target_objects["schema"] = sources[0].get("schema", "bronze")
                target_objects["table"] = sources[0].get("table_name", "")
            elif models:
                model_name = models[0]
                if model_name.startswith("silver_"):
                    target_objects["schema"] = "silver"
                target_objects["table"] = model_name

        # ── Get column from signals if not set ──────────────
        objects_ref = signals.get("objects_referenced", {})
        if not target_objects.get("column") and objects_ref and objects_ref.get("columns"):
            target_objects["column"] = objects_ref["columns"][0]

        # ── Choose evidence collection strategy ─────────────
        check_priorities = target_objects.get("check_priorities", [])
        parsed_question = signals.get("parsed_question", {})
        multi_layer_tables = parsed_question.get("tables_to_check", [])

        if check_priorities and multi_layer_tables:
            # Question-based path: run checks across all layers
            evidence = _run_multi_layer_checks(pg, check_priorities, multi_layer_tables, target_objects)
        elif target_objects.get("table"):
            # Log-based path: run checks for the failure class
            evidence = run_checks_for_class(pg, failure_class, target_objects)
            logger.info(
                "[EVIDENCE] Ran %d checks on %s.%s",
                len(evidence),
                target_objects.get("schema", "?"),
                target_objects.get("table", "?"),
            )
        else:
            logger.warning("[EVIDENCE] No target table identified, skipping direct checks")
            evidence = []

        # ── Run upstream checks (for log-based path) ────────
        upstream_evidence = []
        if not multi_layer_tables:
            # Only run upstream checks for log-based path
            # Multi-layer already covers all tables
            upstream_evidence = _run_lineage_upstream_checks(pg, lineage, target_objects)

        # ── Log summary ─────────────────────────────────────
        for e in evidence:
            ctx = e.get("context", "")
            prefix = f"[{ctx}] " if ctx else ""
            if e.get("error"):
                logger.info("  %s[%s] ERROR: %s", prefix, e["template"], e["error"])
            elif e.get("rows"):
                logger.info("  %s[%s] %s", prefix, e["template"], e["rows"])
            else:
                logger.info("  %s[%s] no anomalies", prefix, e["template"])

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


def _run_multi_layer_checks(
    pg: PostgresConnector,
    priorities: list[str],
    tables: list[dict],
    base_target: dict,
) -> list[dict]:
    """Run evidence checks across all pipeline layers.

    Checks each table from the question parser's tables_to_check list
    with the same set of priorities. This reveals which layer the issue
    originates from.

    For example, if partition_check returns:
        bronze.sales: 0 rows for 2026-03-04
        silver.silver_sales: 0 rows for 2026-03-04
        gold.fct_sales: 0 rows for 2026-03-04
    → Issue originates at bronze (source data missing)

    But if:
        bronze.sales: 16 rows for 2026-03-04
        silver.silver_sales: 0 rows for 2026-03-04
    → Issue is in the bronze → silver transformation
    """
    logger.info(
        "[EVIDENCE] Running multi-layer checks: %s across %d tables",
        priorities,
        len(tables),
    )

    all_results = []

    for table_info in tables:
        schema = table_info.get("schema", "public")
        table = table_info.get("table", "")
        layer = table_info.get("layer", schema)

        if not table:
            continue

        # Build target for this specific table
        layer_target = dict(base_target)
        layer_target["schema"] = schema
        layer_target["table"] = table

        context_label = f"{layer}:{schema}.{table}"
        logger.info("[EVIDENCE] Checking %s", context_label)

        for priority in priorities:
            template_name = _priority_to_template(priority)
            if not template_name:
                continue

            result = run_evidence_check(pg, template_name, layer_target)

            # Skip if missing required parameters
            if result.get("error") and "Missing parameter" in str(result.get("error", "")):
                logger.debug(
                    "[EVIDENCE] Skipping %s on %s — missing params",
                    template_name,
                    context_label,
                )
                continue

            result["context"] = context_label
            result["layer"] = layer
            all_results.append(result)

    # Summarize findings per layer
    _log_layer_summary(all_results)

    return all_results


def _run_lineage_upstream_checks(
    pg: PostgresConnector,
    lineage: dict,
    target_objects: dict,
) -> list[dict]:
    """Run upstream checks based on lineage (for log-based investigations)."""
    upstream_sources = lineage.get("upstream_sources", [])
    upstream_models = lineage.get("upstream_models", [])

    upstream_tables = []
    for source in upstream_sources:
        upstream_tables.append({
            "schema": source.get("schema", "bronze"),
            "table_name": source.get("table_name"),
        })
    for model_name in upstream_models:
        if model_name.startswith("silver_"):
            upstream_tables.append({"schema": "silver", "table_name": model_name})
        else:
            upstream_tables.append({"schema": "public", "table_name": model_name})

    if not upstream_tables:
        return []

    column = target_objects.get("column")
    upstream_evidence = run_upstream_checks(pg, upstream_tables, column=column)
    logger.info(
        "[EVIDENCE] Ran %d upstream checks on %d tables",
        len(upstream_evidence),
        len(upstream_tables),
    )
    return upstream_evidence


def _priority_to_template(priority: str) -> str | None:
    """Map a check priority name to a query template name."""
    mapping = {
        "partition_check": "partition_check",
        "row_count": "row_count",
        "freshness": "freshness",
        "null_check": "null_check",
        "duplicate_check": "duplicate_check",
        "column_presence": "column_presence",
        "invalid_cast_check": "invalid_cast_check",
    }
    return mapping.get(priority)


def _log_layer_summary(results: list[dict]) -> None:
    """Log a summary of findings grouped by layer."""
    layers = {}
    for r in results:
        layer = r.get("layer", "unknown")
        if layer not in layers:
            layers[layer] = []
        layers[layer].append(r)

    for layer in ["bronze", "silver", "gold"]:
        if layer not in layers:
            continue
        findings = layers[layer]
        logger.info("[EVIDENCE] === %s layer ===", layer.upper())
        for f in findings:
            if f.get("error"):
                logger.info("  [%s] ERROR: %s", f["template"], f["error"][:80])
            elif f.get("rows"):
                logger.info("  [%s] %s", f["template"], f["rows"])
            else:
                logger.info("  [%s] no anomalies", f["template"])