"""
context_collector.py — Node 2: Context Collector

Fetches evidence from all available sources:
    - Airflow logs and task metadata
    - dbt manifest, run results, model SQL, lineage
    - Database metadata (INFORMATION_SCHEMA)

Sets availability flags for downstream nodes.
This is pure connector code, no LLM call.

"""

import logging

from agent.state import InvestigationState
from agent.connectors.airflow_connector import AirflowConnector
from agent.connectors.dbt_connector import DbtConnector
from agent.connectors.postgres_connector import PostgresConnector

logger = logging.getLogger(__name__)


def context_collector_node(state: InvestigationState) -> dict:
    """Context Collector — gathers evidence from all sources.

    Reads: dag_id, task_id, run_id, dbt_model
    Writes: logs_raw, logs_available, pipeline_metadata,
            dbt_manifest_entry, dbt_run_result, database_metadata,
            code_context, lineage_context
    """
    dag_id = state.get("dag_id", "")
    task_id = state.get("task_id", "")
    run_id = state.get("run_id", "")
    dbt_model = state.get("dbt_model")

    updates = {}

    # ── Airflow context ─────────────────────────────────────
    logger.info("[CONTEXT] Fetching Airflow logs and metadata...")
    try:
        airflow = AirflowConnector()
        airflow_context = airflow.collect_context(dag_id, run_id, task_id)

        updates["logs_raw"] = airflow_context.get("logs_raw", "")
        updates["logs_available"] = airflow_context.get("logs_available", False)
        updates["pipeline_metadata"] = {
            "task_instance": airflow_context.get("task_instance", {}),
            "dag_run": airflow_context.get("dag_run", {}),
            "dag_details": airflow_context.get("dag_details", {}),
            "all_task_instances": airflow_context.get("all_task_instances", []),
        }

        log_lines = len(updates["logs_raw"].splitlines()) if updates["logs_raw"] else 0
        logger.info("[CONTEXT] Airflow logs: %d lines", log_lines)
    except Exception as e:
        logger.error("[CONTEXT] Airflow context collection failed: %s", e)
        updates["logs_raw"] = ""
        updates["logs_available"] = False
        updates["pipeline_metadata"] = {}

    # ── dbt context ─────────────────────────────────────────
    if dbt_model:
        logger.info("[CONTEXT] Reading dbt artifacts for model: %s", dbt_model)
        try:
            dbt = DbtConnector()
            dbt_context = dbt.collect_context(dbt_model)

            updates["dbt_manifest_entry"] = dbt_context.get("dbt_manifest_entry", {})
            updates["dbt_run_result"] = dbt_context.get("run_result", {})
            updates["code_context"] = dbt_context.get("model_sql", "")
            updates["lineage_context"] = dbt_context.get("lineage_context", {})

            logger.info(
                "[CONTEXT] dbt manifest: %s, SQL: %d lines, lineage: %s",
                "found" if updates["dbt_manifest_entry"] else "not found",
                len(updates["code_context"].splitlines()) if updates["code_context"] else 0,
                updates["lineage_context"].get("upstream_models", []),
            )
        except Exception as e:
            logger.error("[CONTEXT] dbt context collection failed: %s", e)
            updates["dbt_manifest_entry"] = {}
            updates["dbt_run_result"] = {}
            updates["code_context"] = ""
            updates["lineage_context"] = {}
    else:
        logger.info("[CONTEXT] No dbt model resolved — skipping dbt context")
        updates["dbt_manifest_entry"] = {}
        updates["dbt_run_result"] = {}
        updates["code_context"] = ""
        updates["lineage_context"] = {}

    # ── Database metadata ───────────────────────────────────
    logger.info("[CONTEXT] Querying database metadata...")
    try:
        pg = PostgresConnector()


        db_metadata = {}

        # Get metadata for target tables based on lineage
        lineage = updates.get("lineage_context", {})
        #print("\n\n\n","LINEAGE","\n", lineage, "\n\n\n","LINEAGE END") # <---- Delete Later.
        tables_to_check = []

        # Add upstream sources
        for source in lineage.get("upstream_sources", []):
            tables_to_check.append({
                "schema": source.get("schema", "public"),
                "table": source.get("table_name"),
            })

        # Add upstream models
        for model_name in lineage.get("upstream_models", []):
            # Determine schema from dbt config
            model_entry = DbtConnector().get_model_entry(model_name)
            schema = model_entry.get("schema", "public")
            tables_to_check.append({"schema": schema, "table": model_name})

        for table_info in tables_to_check:
            schema = table_info["schema"]
            table = table_info["table"]
            if table:
                key = f"{schema}.{table}"
                db_metadata[key] = pg.collect_metadata(table, schema)

        updates["database_metadata"] = db_metadata
        logger.info("[CONTEXT] Database metadata collected for %d tables", len(db_metadata))
    except Exception as e:
        logger.error("[CONTEXT] Database metadata collection failed: %s", e)
        updates["database_metadata"] = {}
        
    #print("\n\n\n","UPDATES","\n", updates, "\n\n\n","UPDATES END") # <---- Delete Later.
    return updates
