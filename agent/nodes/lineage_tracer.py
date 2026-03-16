"""
lineage_tracer.py — Node 8: Lineage Tracer

Pure code, no LLM. Reads dbt manifest to build upstream and downstream
dependency lists. Identifies which upstream sources feed into the
failing model and which downstream models would be affected.

"""

import logging

from agent.state import InvestigationState
from agent.connectors.dbt_connector import DbtConnector

logger = logging.getLogger(__name__)


def lineage_tracer_node(state: InvestigationState) -> dict:
    """Lineage Tracer — maps the dependency chain.

    Reads: dbt_model, lineage_context (from context collector)
    Writes: lineage_trace
    """
    dbt_model = state.get("dbt_model")
    existing_lineage = state.get("lineage_context", {})

    if not dbt_model:
        logger.info("[LINEAGE] No dbt model, skipping lineage trace")
        return {"lineage_trace": {}}

    logger.info("[LINEAGE] Tracing lineage for %s...", dbt_model)

    try:
        dbt = DbtConnector()

        # Build lineage if not already available from context collector
        if existing_lineage and existing_lineage.get("upstream_models"):
            lineage = dict(existing_lineage)
        else:
            lineage = dbt.build_lineage(dbt_model)

        # Enrich with upstream model details
        upstream_details = []
        for model_name in lineage.get("upstream_models", []):
            entry = dbt.get_model_entry(model_name)
            if entry:
                upstream_details.append({
                    "model": model_name,
                    "schema": entry.get("schema", ""),
                    "description": entry.get("description", ""),
                    "depends_on_sources": [
                        s.split(".")[-1]
                        for s in entry.get("depends_on", {}).get("nodes", [])
                        if s.startswith("source.")
                    ],
                })

        lineage["upstream_details"] = upstream_details

        # Build the dependency chain string for readability
        sources = [
            f"{s.get('schema', 'bronze')}.{s.get('table_name', '?')}"
            for s in lineage.get("upstream_sources", [])
        ]
        models = lineage.get("upstream_models", [])
        downstream = lineage.get("downstream_models", [])

        chain_parts = []
        if sources:
            chain_parts.append(" + ".join(sources))
        if models:
            chain_parts.append(" + ".join(models))
        chain_parts.append(dbt_model)
        if downstream:
            chain_parts.append(" + ".join(downstream))

        lineage["dependency_chain"] = " → ".join(chain_parts)

        logger.info("[LINEAGE] %s", lineage["dependency_chain"])

        return {"lineage_trace": lineage}

    except Exception as e:
        logger.error("[LINEAGE] Lineage tracing failed: %s", e)
        return {"lineage_trace": existing_lineage or {}}
