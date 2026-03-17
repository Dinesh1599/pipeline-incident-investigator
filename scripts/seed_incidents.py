"""
seed_incidents.py — Loads seed incident records into investigator_db
and generates embeddings for vector similarity search.

Usage:
    python scripts/seed_incidents.py

Requires:
    - OPENAI_API_KEY environment variable
    - PostgreSQL (investigator_db) running and accessible
    - incidents table created (via init_db.sql)

"""

import json
import os
import sys
import time

# Add project root to path so we can import agent modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.memory.incident_store import insert_incident, get_incident
from agent.memory.embedding_service import (
    build_embedding_text,
    generate_embedding,
    store_incident_embedding,
)

from dotenv import load_dotenv
load_dotenv()



SEED_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agent", "memory", "seed_incidents.json",
)


def load_seed_incidents() -> None:
    with open(SEED_FILE, "r") as f:
        seeds = json.load(f)

    print(f"Loading {len(seeds)} seed incidents...\n")

    for seed in seeds:
        # Insert the incident record
        incident_id = insert_incident(seed)

        # Build the text for embedding (summary + root cause)
        embedding_text = build_embedding_text(
            seed["summary"],
            seed["root_cause"],
        )

        # Generate and store the embedding
        embedding = generate_embedding(embedding_text)
        store_incident_embedding(incident_id, embedding)

        print(f"  {incident_id}: {seed['failure_class']:20s} — loaded + embedded")

        # Small delay to respect rate limits
        time.sleep(0.2)

    print(f"\nDone. {len(seeds)} seed incidents loaded into investigator_db.")


def verify_retrieval() -> None:
    """Quick test: search for a null-key related incident and check results."""
    from agent.memory.embedding_service import search_similar_incidents

    print("\n--- Verification: searching for 'null customer_id join failure' ---\n")

    results = search_similar_incidents(
        query_text="null customer_id values in bronze table caused NOT NULL constraint violation in fct_sales",
        top_k=3,
    )

    for r in results:
        print(f"  {r['incident_id']} (similarity: {r['similarity_score']:.4f})")
        print(f"    class: {r['failure_class']}")
        print(f"    summary: {r['summary'][:100]}...")
        print()

    if results and results[0]["incident_id"] == "SEED-001":
        print("Verification PASSED: SEED-001 ranked first as expected.")
    elif results:
        print(f"Verification NOTE: {results[0]['incident_id']} ranked first "
              f"(expected SEED-001). Review embeddings.")
    else:
        print("Verification FAILED: No results returned.")


if __name__ == "__main__":
    load_seed_incidents()
    verify_retrieval()
