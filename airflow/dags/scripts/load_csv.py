"""
load_csv.py — Loads a CSV file into a bronze table in pipeline_db.

Usage:
    python load_csv.py <table_name> <csv_path>

Example:
    python load_csv.py bronze_sales /data/seeds/raw_sales.csv

The script truncates the target table first, then loads the CSV.
All bronze table columns are TEXT so any CSV data loads without type errors.
"""

import os
import sys

import psycopg2


def load_csv(table_name: str, csv_path: str) -> None:
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("PIPELINE_DB", "pipeline_db"),
        user=os.environ.get("POSTGRES_USER", "airflow"),
        password=os.environ.get("POSTGRES_PASSWORD", "airflow"),
    )
    try:
        cur = conn.cursor()
        cur.execute(f"TRUNCATE TABLE {table_name} CASCADE")
        with open(csv_path, "r") as f:
            cur.copy_expert(
                f"COPY {table_name} FROM STDIN WITH CSV HEADER NULL ''", f
            )
        conn.commit()
        row_count_query = f"SELECT COUNT(*) FROM {table_name}"
        cur.execute(row_count_query)
        count = cur.fetchone()[0]
        print(f"Loaded {count} rows into {table_name} from {csv_path}")
        cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python load_csv.py <table_name> <csv_path>")
        sys.exit(1)

    load_csv(sys.argv[1], sys.argv[2])
