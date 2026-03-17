"""
signal_extractor.py — Node 3: Signal Extractor

Two paths:
    1. Log-based: Truncates log, runs regex + LLM extraction
    2. Question-based: Discovers pipeline tables, sends question
       to dedicated question parser

"""

import logging

from agent.state import InvestigationState
from agent.prompts import extraction
from agent.prompts import question_parser
from agent.evidence.log_parser import truncate_log, extract_signals_regex
from agent.connectors.postgres_connector import PostgresConnector
from agent.utils.config import MODELS
from agent.utils.context_budget import get_output_budget
from agent.utils.llm_caller import call_llm_json

logger = logging.getLogger(__name__)

# Schemas that represent medallion layers
MEDALLION_SCHEMAS = ["bronze", "silver", "gold", "raw", "staging", "clean", "intermediate", "mart", "analytics"]


def signal_extractor_node(state: InvestigationState) -> dict:
    """Signal Extractor — extracts structured signals from logs or questions.

    Reads: logs_raw, logs_available, error_message, question, dbt_model,
           lineage_context
    Writes: extracted_signals, target_objects
    """
    logs_raw = state.get("logs_raw", "")
    error_message = state.get("error_message", "")
    question = state.get("question", "")
    dbt_model = state.get("dbt_model")

    # ── Path 1: Log-based extraction ────────────────────────
    if logs_raw or error_message:
        return _extract_from_logs(logs_raw, error_message, dbt_model, state)

    # ── Path 2: Question-based extraction ───────────────────
    if question:
        return _extract_from_question(question, dbt_model, state)

    # ── No input available ──────────────────────────────────
    logger.info("[SIGNALS] No logs, error message, or question available")
    return {
        "extracted_signals": {},
        "target_objects": {"date_column": "order_date", "timestamp_column": "order_date"},
    }


def _extract_from_logs(
    logs_raw: str,
    error_message: str,
    dbt_model: str | None,
    state: InvestigationState,
) -> dict:
    """Extract signals from log text using regex + LLM."""
    log_text = logs_raw or error_message
    regex_signals = extract_signals_regex(log_text) if log_text else {}

    truncated_log = truncate_log(logs_raw) if logs_raw else error_message

    llm_signals = {}
    if truncated_log:
        logger.info("[SIGNALS] Calling GPT-4o-mini for signal extraction...")
        user_msg = extraction.build_user_message(truncated_log, regex_signals)
        llm_signals = call_llm_json(
            model=MODELS["signal_extraction"],
            system_prompt=extraction.SYSTEM_PROMPT,
            user_message=user_msg,
            max_tokens=get_output_budget("signal_extraction"),
            node_name="SIGNALS",
        )
        if llm_signals:
            logger.info("[SIGNALS] Extracted: %s", llm_signals.get("error_type", "unknown"))
        else:
            logger.warning("[SIGNALS] LLM extraction returned no results, using regex only")

    merged = _merge_signals(llm_signals, regex_signals)
    target_objects = _build_target_objects_from_signals(merged, state)

    logger.info(
        "[SIGNALS] Final: type=%s, objects=%s",
        merged.get("error_type"),
        merged.get("objects_referenced"),
    )

    return {
        "extracted_signals": merged,
        "target_objects": target_objects,
    }


def _extract_from_question(
    question: str,
    dbt_model: str | None,
    state: InvestigationState,
) -> dict:
    """Extract investigation targets from a user question."""
    logger.info("[SIGNALS] Parsing user question: '%s'", question[:100])

    # Discover available tables from the database
    available_tables = _discover_pipeline_tables()

    lineage = state.get("lineage_context", {})
    pipeline_context = {
        "model": dbt_model,
        "upstream_models": lineage.get("upstream_models", []),
        "upstream_sources": lineage.get("upstream_sources", []),
    }

    user_msg = question_parser.build_user_message(
        question,
        pipeline_context=pipeline_context,
        available_tables=available_tables,
    )

    parsed = call_llm_json(
        model=MODELS["signal_extraction"],
        system_prompt=question_parser.SYSTEM_PROMPT,
        user_message=user_msg,
        max_tokens=get_output_budget("signal_extraction"),
        node_name="SIGNALS",
    )

    if not parsed:
        logger.warning("[SIGNALS] Question parsing returned no results")
        return {
            "extracted_signals": {"question": question},
            "target_objects": {"date_column": "order_date", "timestamp_column": "order_date"},
        }

    # Build extracted_signals from parsed question
    signals = {
        "error_type": None,
        "error_message": None,
        "sql_state_code": None,
        "objects_referenced": {
            "tables": [
                f"{t['schema']}.{t['table']}"
                for t in parsed.get("tables_to_check", [])
            ],
            "columns": parsed.get("columns_of_interest", []),
            "models": [],
        },
        "question": question,
        "investigation_type": parsed.get("investigation_type", "unknown"),
        "parsed_question": parsed,
    }

    target_objects = _build_target_objects_from_question(parsed, state)

    logger.info(
        "[SIGNALS] Parsed question: type=%s, tables=%s, date=%s",
        parsed.get("investigation_type"),
        [f"{t['schema']}.{t['table']}" for t in parsed.get("tables_to_check", [])],
        parsed.get("date_filter", {}).get("value"),
    )

    return {
        "extracted_signals": signals,
        "target_objects": target_objects,
    }


def _discover_pipeline_tables() -> list[dict]:
    """Discover all tables across medallion schemas from the database.

    Queries INFORMATION_SCHEMA to find all tables in schemas that
    match medallion layer naming conventions, along with their columns.
    Works with any medallion architecture setup.
    """
    try:
        pg = PostgresConnector()

        # First, find all schemas that look like medallion layers
        schema_result = pg.execute_query(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast') "
            "ORDER BY schema_name"
        )

        if not schema_result["rows"]:
            return []

        available = []

        for row in schema_result["rows"]:
            schema = row["schema_name"]

            # Get all tables in this schema
            table_result = pg.execute_query(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
                "ORDER BY table_name",
                (schema,),
            )

            for table_row in table_result["rows"]:
                table_name = table_row["table_name"]

                # Get columns for this table
                col_result = pg.execute_query(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s "
                    "ORDER BY ordinal_position",
                    (schema, table_name),
                )

                columns = [c["column_name"] for c in col_result["rows"]]

                # Get date range for date columns
                date_range = None
                date_cols = [c for c in columns if "date" in c.lower() or "time" in c.lower()]
                if date_cols:
                    range_result = pg.execute_query(
                        f"SELECT MIN({date_cols[0]}) AS min_date, MAX({date_cols[0]}) AS max_date "
                        f"FROM {schema}.{table_name} LIMIT 1"
                    )
                    if range_result["rows"]:
                        date_range = {
                            "column": date_cols[0],
                            "min": str(range_result["rows"][0].get("min_date", "")),
                            "max": str(range_result["rows"][0].get("max_date", "")),
                        }

                available.append({
                    "schema": schema,
                    "table": table_name,
                    "columns": columns,
                    "date_range": date_range,
                })

                available.append({
                    "schema": schema,
                    "table": table_name,
                    "columns": columns,
                })

        logger.info(
            "[SIGNALS] Discovered %d tables across schemas: %s",
            len(available),
            list(set(t["schema"] for t in available)),
        )

        return available

    except Exception as e:
        logger.error("[SIGNALS] Failed to discover pipeline tables: %s", e)
        return []


def _build_target_objects_from_question(parsed: dict, state: InvestigationState) -> dict:
    """Build target objects from parsed question output."""
    target = {}

    tables = parsed.get("tables_to_check", [])
    if tables:
        target["schema"] = tables[0].get("schema", "bronze")
        target["table"] = tables[0].get("table", "")

    columns = parsed.get("columns_of_interest", [])
    if columns:
        target["column"] = columns[0]

    date_filter = parsed.get("date_filter", {})
    if date_filter.get("value"):
        target["date_value"] = date_filter["value"]
    if date_filter.get("column"):
        target["date_column"] = date_filter["column"]
    else:
        target["date_column"] = "order_date"

    target.setdefault("timestamp_column", target.get("date_column", "order_date"))
    target["check_priorities"] = parsed.get("check_priorities", [])

    return target


def _build_target_objects_from_signals(signals: dict, state: InvestigationState) -> dict:
    """Build target objects from log-based signal extraction."""
    objects = signals.get("objects_referenced", {})
    lineage = state.get("lineage_context", {})

    target = {}

    if objects and objects.get("tables"):
        table_ref = objects["tables"][0]
        if "." in table_ref:
            target["schema"], target["table"] = table_ref.split(".", 1)
        else:
            target["table"] = table_ref
            target["schema"] = "public"
    elif lineage.get("upstream_sources"):
        source = lineage["upstream_sources"][0]
        target["schema"] = source.get("schema", "bronze")
        target["table"] = source.get("table_name", "")

    if objects and objects.get("columns"):
        target["column"] = objects["columns"][0]

    target.setdefault("date_column", "order_date")
    target.setdefault("timestamp_column", "order_date")

    return target


def _merge_signals(llm_signals: dict, regex_signals: dict) -> dict:
    """Merge LLM extraction with regex extraction."""
    if not llm_signals:
        return regex_signals or {}

    merged = dict(llm_signals)

    if not merged.get("error_type") and regex_signals.get("error_type"):
        merged["error_type"] = regex_signals["error_type"]

    if not merged.get("sql_state_code") and regex_signals.get("sql_state_code"):
        merged["sql_state_code"] = regex_signals["sql_state_code"]

    llm_objects = merged.get("objects_referenced", {})
    regex_objects = regex_signals.get("objects_referenced", {})

    for key in ["tables", "columns", "models"]:
        llm_list = llm_objects.get(key, [])
        regex_list = regex_objects.get(key, [])
        combined = list(set(llm_list + regex_list))
        if "objects_referenced" not in merged:
            merged["objects_referenced"] = {}
        merged["objects_referenced"][key] = combined

    if regex_signals.get("regex_matches"):
        merged["regex_matches"] = regex_signals["regex_matches"]

    return merged