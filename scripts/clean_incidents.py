"""
clean_incidents.py — Remove agent-generated incidents from the database.

Keeps SEED-* records intact. Useful when re-running scenarios to
avoid contaminating retrieval results with previous bad diagnoses.

Usage:
    python scripts/clean_incidents.py
    python scripts/clean_incidents.py --all  # Remove everything including seeds
"""

import os
import sys

import click
import psycopg2
from dotenv import load_dotenv

load_dotenv(".env.local")


@click.command()
@click.option("--all", "remove_all", is_flag=True, help="Remove ALL incidents including seeds")
def main(remove_all):
    """Clean agent-generated incidents from the database."""
    conn = psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["INVESTIGATOR_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    cur = conn.cursor()

    if remove_all:
        cur.execute("DELETE FROM incidents")
        print(f"Deleted {cur.rowcount} incidents (all)")
    else:
        cur.execute("DELETE FROM incidents WHERE incident_id NOT LIKE 'SEED-%%'")
        print(f"Deleted {cur.rowcount} agent-generated incidents (seeds preserved)")

    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
