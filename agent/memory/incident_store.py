"""
incident_store.py — CRUD operations for the incidents table in investigator_db.

Handles inserting new incidents (both seed and auto-generated),
retrieving incident records, and updating validation status.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("INVESTIGATOR_DB", "investigator_db"),
        user=os.environ.get("POSTGRES_USER", "airflow"),
        password=os.environ.get("POSTGRES_PASSWORD", "airflow"),
    )


def insert_incident(incident: dict) -> str:
    """Insert a new incident record. Returns the incident_id."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO incidents (
                incident_id, severity, status, source,
                pipeline_name, dag_id, task_id, run_id,
                failure_class, issue_summary, root_cause,
                confidence, fix_summary, prevention_summary,
                evidence_json, validated
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (incident_id) DO UPDATE SET
                failure_class = EXCLUDED.failure_class,
                issue_summary = EXCLUDED.issue_summary,
                root_cause = EXCLUDED.root_cause,
                confidence = EXCLUDED.confidence,
                fix_summary = EXCLUDED.fix_summary,
                prevention_summary = EXCLUDED.prevention_summary,
                evidence_json = EXCLUDED.evidence_json
            """,
            (
                incident["incident_id"],
                incident.get("severity", "error"),
                incident.get("status", "resolved"),
                incident.get("source", "seed"),
                incident.get("pipeline_name"),
                incident.get("dag_id"),
                incident.get("task_id"),
                incident.get("run_id"),
                incident.get("failure_class"),
                incident.get("summary", incident.get("issue_summary")),
                incident.get("root_cause"),
                incident.get("confidence", 1.0),
                incident.get("fix_applied", incident.get("fix_summary")),
                incident.get("prevention_added", incident.get("prevention_summary")),
                json.dumps(incident.get("evidence_json", {
                    "evidence_summary": incident.get("evidence_summary", ""),
                    "tags": incident.get("tags", []),
                })),
                incident.get("validated", True),
            ),
        )
        conn.commit()
        cur.close()
        return incident["incident_id"]
    finally:
        conn.close()


def get_incident(incident_id: str) -> Optional[dict]:
    """Retrieve a single incident by ID."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT * FROM incidents WHERE incident_id = %s",
            (incident_id,),
        )
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_incidents() -> list[dict]:
    """Retrieve all incidents."""
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM incidents ORDER BY created_at DESC")
        rows = cur.fetchall()
        cur.close()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def mark_validated(incident_id: str, validated: bool = True) -> None:
    """Mark an incident as validated (human-confirmed diagnosis)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE incidents SET validated = %s WHERE incident_id = %s",
            (validated, incident_id),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
