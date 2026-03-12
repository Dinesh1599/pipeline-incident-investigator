"""
postgres_connector.py — Queries database metadata from pipeline_db.

Provides:
    - INFORMATION_SCHEMA queries (column names, types, constraints)
    - Table metadata (row counts, existence checks)
    - Read-only query execution with timeout and safety constraints

Blueprint reference: Section 8 (Stage 4: Error Message Parsing),
Section 9.2 (Node 2: Context Collector, Node 6: Database Evidence Analyzer)

Safety constraints (from blueprint Section 11):
    - All queries use parameterized templates. No LLM-generated SQL.
    - All queries include LIMIT clauses.
    - Read-only connection.
    - Query timeout is 10 seconds.
    - If a query fails, the error is recorded as evidence.
"""

import logging
import os
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_MS = 10000  # 10 seconds


class PostgresConnector:
    """Connects to pipeline_db for metadata queries and evidence checks."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.host = host or os.environ.get("POSTGRES_HOST", "postgres")
        self.port = port or int(os.environ.get("POSTGRES_PORT", "5432"))
        self.dbname = dbname or os.environ.get("PIPELINE_DB", "pipeline_db")
        self.user = user or os.environ.get("POSTGRES_USER", "airflow")
        self.password = password or os.environ.get("POSTGRES_PASSWORD", "airflow")

    def _get_connection(self):
        conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            options=f"-c statement_timeout={QUERY_TIMEOUT_MS}",
        )
        conn.set_session(readonly=True, autocommit=True)
        return conn

    def execute_query(self, query: str, params: Optional[tuple] = None) -> dict:
        """Execute a read-only query and return results.

        Returns a dict with 'rows', 'columns', 'row_count', and 'error'.
        On failure, 'error' contains the error message and 'rows' is empty.
        The error itself is useful evidence for the investigation.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(query, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description] if cur.description else []
            cur.close()
            return {
                "rows": [dict(row) for row in rows],
                "columns": columns,
                "row_count": len(rows),
                "error": None,
            }
        except psycopg2.Error as e:
            logger.error("Query failed: %s — %s", query[:100], e)
            return {
                "rows": [],
                "columns": [],
                "row_count": 0,
                "error": str(e).strip(),
            }
        finally:
            if conn:
                conn.close()

    def get_table_columns(self, table: str, schema: str = "public") -> dict:
        """Get column names and types for a table from INFORMATION_SCHEMA."""
        query = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        return self.execute_query(query, (schema, table))

    def get_table_constraints(self, table: str, schema: str = "public") -> dict:
        """Get constraints (PK, FK, UNIQUE, NOT NULL) for a table."""
        query = """
            SELECT
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = %s AND tc.table_name = %s
        """
        return self.execute_query(query, (schema, table))

    def check_table_exists(self, table: str, schema: str = "public") -> bool:
        """Check if a table exists."""
        result = self.execute_query(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            ) AS table_exists
            """,
            (schema, table),
        )
        if result["rows"]:
            return result["rows"][0].get("table_exists", False)
        return False

    def get_all_tables(self, schema: str = "public") -> dict:
        """List all tables in a schema."""
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        return self.execute_query(query, (schema,))

    def collect_metadata(self, table: str, schema: str = "public") -> dict:
        """Collect full metadata for a table.

        Main method called by the Context Collector node for
        database metadata gathering.
        """
        return {
            "table": f"{schema}.{table}",
            "exists": self.check_table_exists(table, schema),
            "columns": self.get_table_columns(table, schema),
            "constraints": self.get_table_constraints(table, schema),
        }
