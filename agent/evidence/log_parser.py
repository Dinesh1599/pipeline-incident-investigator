"""
log_parser.py — Parses and truncates Airflow task logs for LLM consumption.

Extracts the most relevant portions of a log for investigation:
    - Last N lines of the log
    - Lines containing ERROR, FATAL, WARNING, EXCEPTION
    - Context lines (5 before and after each error line)
    - Deduplicates overlapping line ranges

Also provides regex-based signal extraction for common Postgres and
dbt error patterns, supplementing the LLM signal extraction node.

Blueprint reference: Section 15 (Log Truncation Strategy),
Section 9.2 (Node 3: Signal Extractor)
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── Log Truncation ──────────────────────────────────────────────

TAIL_LINES = 50
CONTEXT_LINES = 5
ERROR_KEYWORDS = ["ERROR", "FATAL", "WARNING", "EXCEPTION", "Traceback"]


def truncate_log(raw_log: str, tail_lines: int = TAIL_LINES) -> str:
    """Truncate a raw log to the most relevant lines.

    From blueprint Section 15:
        - Extract the last 50 lines of the Airflow task log.
        - Additionally extract lines containing ERROR, FATAL, WARNING, EXCEPTION.
        - For each error line, include 5 lines before and after for context.
        - Deduplicate overlapping line ranges.
        - Typically reduces a 5,000-line log to 50-100 relevant lines.

    Args:
        raw_log: The full raw log text.
        tail_lines: Number of lines to keep from the end.

    Returns:
        Truncated log string.
    """
    if not raw_log:
        return ""

    lines = raw_log.splitlines()
    total_lines = len(lines)

    if total_lines <= tail_lines:
        return raw_log

    # Collect line indices to include
    included = set()

    # Always include the last N lines
    for i in range(max(0, total_lines - tail_lines), total_lines):
        included.add(i)

    # Find error lines and add context
    for i, line in enumerate(lines):
        if any(keyword in line for keyword in ERROR_KEYWORDS):
            start = max(0, i - CONTEXT_LINES)
            end = min(total_lines, i + CONTEXT_LINES + 1)
            for j in range(start, end):
                included.add(j)

    # Build the truncated output in order
    sorted_indices = sorted(included)
    result_lines = []
    prev_idx = -2

    for idx in sorted_indices:
        if idx > prev_idx + 1:
            result_lines.append(f"... ({idx - prev_idx - 1} lines omitted) ...")
        result_lines.append(lines[idx])
        prev_idx = idx

    return "\n".join(result_lines)


# ── Regex-Based Signal Extraction ───────────────────────────────

# Common Postgres and dbt error patterns
ERROR_PATTERNS = {
    "not_null_violation": {
        "pattern": r'null value in column "(\w+)".*not-null constraint',
        "error_type": "not_null_violation",
        "sql_state": "23502",
    },
    "type_cast_failure": {
        "pattern": r"invalid input syntax for type (\w+): \"([^\"]+)\"",
        "error_type": "type_cast_failure",
        "sql_state": "22P02",
    },
    "relation_not_found": {
        "pattern": r'relation "([^"]+)" does not exist',
        "error_type": "relation_not_found",
        "sql_state": "42P01",
    },
    "column_not_found": {
        "pattern": r'column "(\w+)" (?:of relation "(\w+)" )?does not exist',
        "error_type": "column_not_found",
        "sql_state": "42703",
    },
    "permission_denied": {
        "pattern": r"permission denied for (\w+) (\w+)",
        "error_type": "permission_denied",
        "sql_state": "42501",
    },
    "unique_violation": {
        "pattern": r"duplicate key value violates unique constraint",
        "error_type": "unique_violation",
        "sql_state": "23505",
    },
    "dbt_compile_error": {
        "pattern": r"Compilation Error in model (\w+)",
        "error_type": "dbt_compile_error",
        "sql_state": None,
    },
    "dbt_database_error": {
        "pattern": r"Database Error in model (\w+)",
        "error_type": "dbt_database_error",
        "sql_state": None,
    },
    "invalid_date": {
        "pattern": r'invalid input syntax for type date: "([^"]+)"',
        "error_type": "type_cast_failure",
        "sql_state": "22007",
    },
}

# Patterns for extracting referenced objects
OBJECT_PATTERNS = {
    "table_reference": re.compile(
        r'(?:relation|table|from|join|into)\s+"?(\w+)"?\."?(\w+)"?',
        re.IGNORECASE,
    ),
    "column_reference": re.compile(
        r'column "(\w+)"',
        re.IGNORECASE,
    ),
    "model_reference": re.compile(
        r'model (\w+)',
        re.IGNORECASE,
    ),
}


def extract_signals_regex(log_text: str) -> dict:
    """Extract structured signals from log text using regex patterns.

    This supplements the LLM-based signal extraction (Node 3).
    Regex catches well-known patterns quickly and reliably;
    the LLM handles anything regex misses.

    Returns:
        Dict with error_type, error_message, referenced objects,
        sql_state_code, and matched patterns.
    """
    signals = {
        "error_type": None,
        "error_message": None,
        "sql_state_code": None,
        "objects_referenced": {
            "tables": [],
            "columns": [],
            "models": [],
        },
        "regex_matches": [],
    }

    # Match against known error patterns
    for pattern_name, pattern_info in ERROR_PATTERNS.items():
        match = re.search(pattern_info["pattern"], log_text, re.IGNORECASE)
        if match:
            signals["error_type"] = pattern_info["error_type"]
            signals["error_message"] = match.group(0)
            signals["sql_state_code"] = pattern_info["sql_state"]
            signals["regex_matches"].append({
                "pattern": pattern_name,
                "match": match.group(0),
                "groups": match.groups(),
            })

    # Extract referenced objects
    for match in OBJECT_PATTERNS["table_reference"].finditer(log_text):
        table_ref = f"{match.group(1)}.{match.group(2)}"
        if table_ref not in signals["objects_referenced"]["tables"]:
            signals["objects_referenced"]["tables"].append(table_ref)

    for match in OBJECT_PATTERNS["column_reference"].finditer(log_text):
        col = match.group(1)
        if col not in signals["objects_referenced"]["columns"]:
            signals["objects_referenced"]["columns"].append(col)

    for match in OBJECT_PATTERNS["model_reference"].finditer(log_text):
        model = match.group(1)
        if model not in signals["objects_referenced"]["models"]:
            signals["objects_referenced"]["models"].append(model)

    return signals


def extract_error_lines(log_text: str) -> list[str]:
    """Extract only the lines containing error keywords.

    Useful for a quick summary of what went wrong without
    the full context.
    """
    if not log_text:
        return []

    return [
        line.strip()
        for line in log_text.splitlines()
        if any(keyword in line for keyword in ERROR_KEYWORDS)
    ]
