"""
signal_extractor.py — Node 3: Signal Extractor

Sends the raw log (pre-truncated) to GPT-4o-mini with a structured
extraction prompt. Also runs regex-based extraction as a supplement.
Merges LLM extraction with regex extraction.

Blueprint reference: Section 9.2 (Node 3), Section 10.1
"""

import json
import logging

from langchain_openai import ChatOpenAI

from agent.state import InvestigationState
from agent.prompts import extraction
from agent.evidence.log_parser import truncate_log, extract_signals_regex
from agent.utils.config import MODELS, LLM_TEMPERATURE, LLM_MAX_RETRIES
from agent.utils.context_budget import get_output_budget

logger = logging.getLogger(__name__)


def parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def signal_extractor_node(state: InvestigationState) -> dict:
    """Signal Extractor — extracts structured signals from logs.

    Reads: logs_raw, logs_available, error_message
    Writes: extracted_signals, target_objects
    """
    logs_raw = state.get("logs_raw", "")
    logs_available = state.get("logs_available", False)
    error_message = state.get("error_message", "")
    dbt_model = state.get("dbt_model")

    # ── Regex extraction (always runs) ──────────────────────
    log_text = logs_raw or error_message
    regex_signals = extract_signals_regex(log_text) if log_text else {}

    # ── Log truncation ──────────────────────────────────────
    truncated_log = truncate_log(logs_raw) if logs_raw else error_message

    # ── LLM extraction ──────────────────────────────────────
    llm_signals = {}

    if truncated_log:
        logger.info("[SIGNALS] Calling GPT-4o-mini for signal extraction...")
        try:
            llm = ChatOpenAI(
                model=MODELS["signal_extraction"],
                temperature=LLM_TEMPERATURE,
                max_tokens=get_output_budget("signal_extraction"),
            )

            user_msg = extraction.build_user_message(truncated_log, regex_signals)
            response = llm.invoke([
                {"role": "system", "content": extraction.SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ])

            llm_signals = parse_json_response(response.content)
            logger.info("[SIGNALS] Extracted: %s", llm_signals.get("error_type", "unknown"))

        except json.JSONDecodeError:
            logger.warning("[SIGNALS] LLM returned malformed JSON, retrying...")
            try:
                retry_response = llm.invoke([
                    {"role": "system", "content": extraction.SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        "Your previous response was not valid JSON. "
                        "Respond with ONLY valid JSON matching the schema.\n\n"
                        + user_msg
                    )},
                ])
                llm_signals = parse_json_response(retry_response.content)
            except Exception:
                logger.error("[SIGNALS] Retry failed, falling back to regex only")
                llm_signals = {}

        except Exception as e:
            logger.error("[SIGNALS] LLM extraction failed: %s", e)
            llm_signals = {}
    else:
        logger.info("[SIGNALS] No log text available, using regex signals only")

    # ── Merge LLM and regex signals ─────────────────────────
    merged = _merge_signals(llm_signals, regex_signals)

    # ── Build target objects for evidence checks ────────────
    target_objects = _build_target_objects(merged, state)

    logger.info(
        "[SIGNALS] Final: type=%s, objects=%s",
        merged.get("error_type"),
        merged.get("objects_referenced"),
    )

    return {
        "extracted_signals": merged,
        "target_objects": target_objects,
    }


def _merge_signals(llm_signals: dict, regex_signals: dict) -> dict:
    """Merge LLM extraction with regex extraction.

    LLM signals take priority. Regex fills in gaps.
    Objects are combined from both sources.
    """
    if not llm_signals:
        return regex_signals or {}

    merged = dict(llm_signals)

    # Fill missing fields from regex
    if not merged.get("error_type") and regex_signals.get("error_type"):
        merged["error_type"] = regex_signals["error_type"]

    if not merged.get("sql_state_code") and regex_signals.get("sql_state_code"):
        merged["sql_state_code"] = regex_signals["sql_state_code"]

    # Merge object references
    llm_objects = merged.get("objects_referenced", {})
    regex_objects = regex_signals.get("objects_referenced", {})

    for key in ["tables", "columns", "models"]:
        llm_list = llm_objects.get(key, [])
        regex_list = regex_objects.get(key, [])
        combined = list(set(llm_list + regex_list))
        if "objects_referenced" not in merged:
            merged["objects_referenced"] = {}
        merged["objects_referenced"][key] = combined

    # Keep regex_matches for downstream reference
    if regex_signals.get("regex_matches"):
        merged["regex_matches"] = regex_signals["regex_matches"]

    return merged


def _build_target_objects(signals: dict, state: InvestigationState) -> dict:
    """Build the target objects dict for evidence queries.

    Determines which schema, table, and column to investigate
    based on extracted signals and lineage context.
    """
    objects = signals.get("objects_referenced", {})
    lineage = state.get("lineage_context", {})

    target = {}

    # Determine target table and schema from signals or lineage
    if objects.get("tables"):
        # Parse schema.table if present
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

    # Determine target column from signals
    if objects.get("columns"):
        target["column"] = objects["columns"][0]

    # Add date-related fields for partition checks
    target.setdefault("date_column", "order_date")
    target.setdefault("timestamp_column", "order_date")

    return target
