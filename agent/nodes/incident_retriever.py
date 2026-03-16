"""
incident_retriever.py — Node 9: Incident Retriever

Embeds the current incident summary using text-embedding-3-small.
Queries pgvector for the top 3 most similar past incidents.
Optionally filters by failure_class for more relevant results.

"""

import logging

from agent.state import InvestigationState
from agent.memory.embedding_service import (
    build_embedding_text,
    search_similar_incidents,
)

logger = logging.getLogger(__name__)


def incident_retriever_node(state: InvestigationState) -> dict:
    """Incident Retriever — finds similar past incidents.

    Reads: extracted_signals, failure_class, dbt_model, question
    Writes: similar_incidents
    """
    signals = state.get("extracted_signals", {})
    failure_class = state.get("failure_class")
    dbt_model = state.get("dbt_model", "")
    question = state.get("question", "")

    # Build a search query from available context
    query_parts = []

    if question:
        query_parts.append(question)

    error_msg = signals.get("error_message", "")
    if error_msg:
        query_parts.append(error_msg)

    error_type = signals.get("error_type", "")
    if error_type and error_type != "unknown":
        query_parts.append(error_type)

    if dbt_model:
        query_parts.append(f"model: {dbt_model}")

    # Referenced objects
    objects = signals.get("objects_referenced", {})
    if objects:
        for col in objects.get("columns", []):
            query_parts.append(col)
        for table in objects.get("tables", []):
            query_parts.append(table)

    if not query_parts:
        query_parts.append(f"{failure_class or 'unknown'} failure in pipeline")

    query_text = " ".join(query_parts)
    logger.info("[RETRIEVAL] Searching for similar incidents: '%s'", query_text[:100])

    try:
        results = search_similar_incidents(
            query_text=query_text,
            failure_class=failure_class,
            top_k=3,
        )

        if results:
            logger.info("[RETRIEVAL] Found %d similar incidents:", len(results))
            for r in results:
                logger.info(
                    "  %s (similarity: %.4f, class: %s)",
                    r["incident_id"],
                    r.get("similarity_score", 0),
                    r.get("failure_class", "?"),
                )
        else:
            logger.info("[RETRIEVAL] No similar incidents found (cold start)")

        return {"similar_incidents": results}

    except Exception as e:
        logger.error("[RETRIEVAL] Incident retrieval failed: %s", e)
        return {"similar_incidents": []}
