"""
embedding_service.py — Generates embeddings using OpenAI text-embedding-3-small
and provides vector similarity search against the incidents table in investigator_db.

Embedding strategy:
    Embed a concatenation of the incident summary and root cause fields.
    This captures both the symptom and the explanation, improving retrieval relevance.
    Cost: ~$0.00002 per embedding.
"""

import os
from typing import Optional

import psycopg2
from openai import OpenAI


EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def get_openai_client() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("INVESTIGATOR_DB", "investigator_db"),
        user=os.environ.get("POSTGRES_USER", "airflow"),
        password=os.environ.get("POSTGRES_PASSWORD", "airflow"),
    )


def generate_embedding(text: str) -> list[float]:
    """Generate a 1536-dimension embedding for the given text."""
    client = get_openai_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def build_embedding_text(summary: str, root_cause: str) -> str:
    """Concatenate summary and root cause for embedding.

    'Embed a concatenation of the incident
    summary and root cause fields. This captures both the symptom and
    the explanation, which improves retrieval relevance.'
    """
    return f"{summary}\n\nRoot cause: {root_cause}"


def store_incident_embedding(incident_id: str, embedding: list[float]) -> None:
    """Store an embedding vector for an existing incident record."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE incidents SET embedding = %s::vector WHERE incident_id = %s",
            (str(embedding), incident_id),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def search_similar_incidents(
    query_text: str,
    failure_class: Optional[str] = None,
    top_k: int = 3,
) -> list[dict]:
    """Find the top-k most similar past incidents using vector cosine similarity.

    'Use hybrid search: vector similarity for
    semantic matching combined with metadata filtering for structural matching.
    Filter by failure_class (if classified), then rank by vector cosine similarity.
    Return top 3 results. Send only summary, root_cause, and fix_applied fields.'

    Args:
        query_text: The current incident summary to search against.
        failure_class: Optional filter to narrow results by failure type.
        top_k: Number of results to return (default 3).

    Returns:
        List of dicts with incident_id, summary, root_cause, fix_applied,
        failure_class, confidence, and similarity_score.
    """
    query_embedding = generate_embedding(query_text)

    conn = get_db_connection()
    try:
        cur = conn.cursor()

        if failure_class:
            cur.execute(
                """
                SELECT
                    incident_id,
                    issue_summary,
                    root_cause,
                    fix_summary,
                    failure_class,
                    confidence,
                    1 - (embedding <=> %s::vector) AS similarity_score
                FROM incidents
                WHERE embedding IS NOT NULL
                  AND failure_class = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (str(query_embedding), failure_class, str(query_embedding), top_k),
            )
        else:
            cur.execute(
                """
                SELECT
                    incident_id,
                    issue_summary,
                    root_cause,
                    fix_summary,
                    failure_class,
                    confidence,
                    1 - (embedding <=> %s::vector) AS similarity_score
                FROM incidents
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (str(query_embedding), str(query_embedding), top_k),
            )

        rows = cur.fetchall()
        cur.close()

        return [
            {
                "incident_id": row[0],
                "summary": row[1],
                "root_cause": row[2],
                "fix_applied": row[3],
                "failure_class": row[4],
                "confidence": row[5],
                "similarity_score": round(row[6], 4) if row[6] else None,
            }
            for row in rows
        ]
    finally:
        conn.close()
