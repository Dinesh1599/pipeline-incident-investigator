"""
query_templates.py — Parameterized SQL evidence check templates.

All queries are pre-defined templates with safe parameter substitution.
No LLM-generated SQL is ever executed.



Template selection logic: Templates are selected based on failure_class
from the classifier. Each class triggers a specific set of templates.

    data_quality       → null_check, duplicate_check, row_count, freshness
    schema_drift       → column_presence, type_check, constraint_check
    code_failure       → sample_rows, invalid_cast_check
    dependency         → partition_check, row_count, freshness
    silent_correctness → row_count, metric_check, null_check, duplicate_check
"""

import logging
from typing import Optional

from agent.connectors.postgres_connector import PostgresConnector

logger = logging.getLogger(__name__)


# ── Template Definitions ────────────────────────────────────────

TEMPLATES = {
    "null_check": {
        "description": "Count null values in a column",
        "sql": "SELECT COUNT(*) AS null_count FROM {schema}.{table} WHERE {column} IS NULL",
    },
    "duplicate_check": {
        "description": "Find duplicate values in a business key column (top 10)",
        "sql": (
            "SELECT {column}, COUNT(*) AS cnt FROM {schema}.{table} "
            "GROUP BY {column} HAVING COUNT(*) > 1 ORDER BY cnt DESC LIMIT 10"
        ),
    },
    "duplicate_total": {
        "description": "Count total number of duplicate keys",
        "sql": (
            "SELECT COUNT(*) AS duplicate_key_count FROM ("
            "SELECT {column} FROM {schema}.{table} "
            "GROUP BY {column} HAVING COUNT(*) > 1"
            ") sub"
        ),
    },
    "row_count": {
        "description": "Total row count for a table",
        "sql": "SELECT COUNT(*) AS total_rows FROM {schema}.{table}",
    },
    "partition_check": {
        "description": "Check if rows exist for a specific date",
        "sql": (
            "SELECT COUNT(*) AS partition_rows FROM {schema}.{table} "
            "WHERE {date_column} = '{date_value}'"
        ),
    },
    "freshness": {
        "description": "Most recent timestamp in the table",
        "sql": "SELECT MAX({timestamp_column}) AS latest_record FROM {schema}.{table}",
    },
    "invalid_cast_check": {
        "description": "Find values that cannot be safely cast to integer",
        "sql": (
            "SELECT {column} FROM {schema}.{table} "
            "WHERE {column} !~ '^[0-9]+$' AND {column} IS NOT NULL LIMIT 20"
        ),
    },
    "column_presence": {
        "description": "Check columns and types for a table",
        "sql": (
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = '{table}' AND table_schema = '{schema}'"
        ),
    },
    "sample_rows": {
        "description": "Sample rows matching a condition",
        "sql": "SELECT * FROM {schema}.{table} WHERE {condition} LIMIT 5",
    },
}


# ── Failure Class to Template Mapping ───────────────────────────

CLASS_TEMPLATES = {
    "data_quality": ["null_check", "duplicate_check", "duplicate_total", "row_count", "freshness"],
    "schema_drift": ["column_presence", "invalid_cast_check"],
    "code_failure": ["sample_rows", "null_check", "row_count"],
    "dependency": ["partition_check", "row_count", "freshness"],
    "silent_correctness": ["row_count", "null_check", "duplicate_check"],
    "resource": ["row_count"],
    "access": ["column_presence"],
}


# ── Query Execution ─────────────────────────────────────────────

def run_evidence_check(
    connector: PostgresConnector,
    template_name: str,
    params: dict,
) -> dict:
    """Run a single evidence check template.

    Args:
        connector: PostgresConnector instance
        template_name: Name of the template (e.g., 'null_check')
        params: Dict of parameters to substitute into the template
            (e.g., {'schema': 'bronze', 'table': 'sales', 'column': 'customer_id'})

    Returns:
        Dict with template name, description, query, results, and any error.
    """
    template = TEMPLATES.get(template_name)
    if not template:
        return {
            "template": template_name,
            "error": f"Unknown template: {template_name}",
        }

    try:
        query = template["sql"].format(**params)
    except KeyError as e:
        return {
            "template": template_name,
            "error": f"Missing parameter for template: {e}",
        }

    result = connector.execute_query(query)

    return {
        "template": template_name,
        "description": template["description"],
        "query": query,
        "rows": result["rows"],
        "row_count": result["row_count"],
        "error": result["error"],
    }


def run_checks_for_class(
    connector: PostgresConnector,
    failure_class: str,
    target_objects: dict,
) -> list[dict]:
    """Run all evidence checks appropriate for a failure class.

    This is the main method called by the Database Evidence Analyzer
    node (Node 6). It selects templates based on the failure class
    and runs them against the target objects.

    Args:
        connector: PostgresConnector instance
        failure_class: The classified failure type (e.g., 'data_quality')
        target_objects: Dict with keys like:
            - schema: Target schema (e.g., 'bronze')
            - table: Target table (e.g., 'sales')
            - column: Target column (e.g., 'customer_id')
            - date_column: Date column for partition checks
            - date_value: Date value to check
            - timestamp_column: Column for freshness checks
            - condition: WHERE condition for sample_rows

    Returns:
        List of evidence check results.
    """
    template_names = CLASS_TEMPLATES.get(failure_class, ["row_count"])
    results = []

    for template_name in template_names:
        # Skip templates that require params we don't have
        template = TEMPLATES.get(template_name)
        if not template:
            continue

        required_params = _extract_params(template["sql"])
        if not all(p in target_objects for p in required_params):
            logger.debug(
                "Skipping %s — missing params: %s",
                template_name,
                [p for p in required_params if p not in target_objects],
            )
            continue

        result = run_evidence_check(connector, template_name, target_objects)
        results.append(result)

    return results


def _extract_params(template_sql: str) -> list[str]:
    """Extract parameter names from a template SQL string."""
    import re
    return list(set(re.findall(r"\{(\w+)\}", template_sql)))


def run_upstream_checks(
    connector: PostgresConnector,
    upstream_tables: list[dict],
    column: Optional[str] = None,
) -> list[dict]:
    """Run basic evidence checks on upstream tables.

    'When direct evidence at the failure point is inconclusive, the agent should check one
    level upstream using dbt depends_on.'

    Args:
        connector: PostgresConnector instance
        upstream_tables: List of dicts with 'schema' and 'table' keys
        column: Optional column to check for nulls/invalids

    Returns:
        List of evidence check results for upstream tables.
    """
    results = []

    for table_info in upstream_tables:
        schema = table_info.get("schema", "public")
        table = table_info.get("table_name", table_info.get("table"))

        if not table:
            continue

        # Always run row count on upstream
        result = run_evidence_check(
            connector, "row_count", {"schema": schema, "table": table}
        )
        result["context"] = f"upstream:{schema}.{table}"
        results.append(result)

        # If a column is specified, check nulls upstream
        if column:
            null_result = run_evidence_check(
                connector,
                "null_check",
                {"schema": schema, "table": table, "column": column},
            )
            null_result["context"] = f"upstream:{schema}.{table}"
            results.append(null_result)

    return results
