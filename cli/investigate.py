"""
investigate.py — CLI entry point for the investigation agent.

Three modes:
    1. Airflow failure: --dag-id, --task-id, --run-id
    2. Free-form question: --question "Why are sales missing?"
    3. Replay: --incident-id INC-xxx (show a stored report)

Streams investigation progress in real time using rich library.

Blueprint reference: Section 18 (CLI Interface Design)

Usage:
    python cli/investigate.py --dag-id sales_pipeline --task-id run_dbt_fct_sales --run-id manual__2026-03-16T09:12:03
    python cli/investigate.py --question "Why are sales missing for March 4th?"
    python cli/investigate.py --incident-id INC-20260316110601-9b53ea
"""

import json
import logging
import sys

import click

from dotenv import load_dotenv
load_dotenv(".env.local")

from cli.display import (
    console,
    print_banner,
    print_step,
    print_report,
    print_error,
    print_success,
)


class StreamingHandler(logging.Handler):
    """Custom log handler that routes agent log messages to the rich display."""

    NODE_PREFIXES = [
        "INTAKE", "CONTEXT", "SIGNALS", "CLASSIFY", "ROUTER",
        "EVIDENCE", "CODE", "LINEAGE", "RETRIEVAL", "REASONING",
        "FIX", "REPORT",
    ]

    def emit(self, record):
        msg = record.getMessage()
        for prefix in self.NODE_PREFIXES:
            if msg.startswith(f"[{prefix}]"):
                # Strip the prefix from message since print_step adds it
                clean_msg = msg[len(prefix) + 3:]  # Remove [PREFIX] and space
                print_step(prefix, clean_msg)
                return
        # Non-node log messages — skip HTTP request noise
        if "HTTP Request:" not in msg and "Airflow API" not in msg:
            if record.levelno >= logging.WARNING:
                print_step("WARN", msg, "yellow")


@click.command()
@click.option("--dag-id", default="sales_pipeline", help="Airflow DAG ID")
@click.option("--task-id", default=None, help="Airflow Task ID that failed")
@click.option("--run-id", default=None, help="Airflow DAG Run ID")
@click.option("--question", "-q", default=None, help="Free-form question about pipeline data")
@click.option("--incident-id", default=None, help="Replay a stored incident report")
@click.option("--output", "-o", default=None, help="Save report to JSON file")
@click.option("--verbose", "-v", is_flag=True, help="Show all log messages")
def investigate(dag_id, task_id, run_id, question, incident_id, output, verbose):
    """Investigate a data pipeline failure or answer a data question."""

    print_banner()
    console.print()

    # ── Mode 1: Replay stored incident ──────────────────────
    if incident_id:
        _replay_incident(incident_id)
        return

    # ── Validate inputs ─────────────────────────────────────
    if not question and not task_id:
        print_error(
            "Provide either --task-id (for failure investigation) "
            "or --question (for data question)."
        )
        console.print()
        console.print("Examples:")
        console.print("  python cli/investigate.py --task-id run_dbt_fct_sales --run-id manual__2026-03-16T09:12:03")
        console.print('  python cli/investigate.py --question "Why are sales missing for March 4th?"')
        sys.exit(1)

    # ── Set up streaming log handler ────────────────────────
    handler = StreamingHandler()
    handler.setLevel(logging.INFO if not verbose else logging.DEBUG)

    # Attach to agent loggers
    for logger_name in ["agent.nodes", "agent.connectors", "agent.memory", "agent.evidence"]:
        logger = logging.getLogger(logger_name)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO if not verbose else logging.DEBUG)

    # Suppress noisy loggers
    for noisy in ["httpx", "openai", "httpcore", "urllib3"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # ── Build trigger payload ───────────────────────────────
    trigger = {
        "pipeline_name": dag_id,
        "dag_id": dag_id,
        "task_id": task_id or "",
        "run_id": run_id or "",
        "severity": "error" if task_id else "warning",
    }

    if question:
        trigger["question"] = question
        trigger["severity"] = "warning"
        console.print(f"[bold]Question:[/bold] {question}")
    else:
        trigger["error_message"] = "Bash command failed. The command returned a non-zero exit code 1."
        console.print(f"[bold]Investigating:[/bold] {dag_id}.{task_id}")
        if run_id:
            console.print(f"[dim]Run ID: {run_id}[/dim]")

    console.print()
    console.print("[bold cyan]Starting investigation...[/bold cyan]")
    console.print()

    # ── Run the graph ───────────────────────────────────────
    from agent.graph import compile_graph

    try:
        app = compile_graph()
        result = app.invoke(trigger)
    except Exception as e:
        print_error(f"Investigation failed: {e}")
        sys.exit(1)

    # ── Display the report ──────────────────────────────────
    report = result.get("final_report", {})

    if report:
        print_report(report)

        # Save to file if requested
        if output:
            with open(output, "w") as f:
                json.dump(report, f, indent=2, default=str)
            print_success(f"Report saved to {output}")
        else:
            # Auto-save with incident ID
            filename = f"{report.get('incident_id', 'report')}.json"
            with open(filename, "w") as f:
                json.dump(report, f, indent=2, default=str)
            print_success(f"Report saved to {filename}")
    else:
        print_error("No report generated — check the logs above for errors.")


def _replay_incident(incident_id: str):
    """Load and display a stored incident report."""
    from agent.memory.incident_store import get_incident

    console.print(f"[bold]Loading incident:[/bold] {incident_id}")
    console.print()

    incident = get_incident(incident_id)
    if not incident:
        print_error(f"Incident {incident_id} not found in database.")
        return

    # Convert stored incident to report format
    report = {
        "incident_id": incident.get("incident_id"),
        "severity": incident.get("severity"),
        "failure_class": incident.get("failure_class"),
        "what_failed": incident.get("issue_summary"),
        "where_failed": {
            "dag_id": incident.get("dag_id"),
            "task_id": incident.get("task_id"),
            "model": "",
            "table": "",
            "column": "",
        },
        "how_it_failed": "",
        "root_cause": incident.get("root_cause"),
        "evidence_chain": incident.get("evidence_json", {}).get("evidence_chain", []),
        "confidence": incident.get("confidence"),
        "alternative_causes_considered": incident.get("evidence_json", {}).get("alternative_causes", []),
        "fix": json.loads(incident.get("fix_summary", "{}")) if isinstance(incident.get("fix_summary"), str) else incident.get("fix_summary", {}),
        "prevention": json.loads(incident.get("prevention_summary", "[]")) if isinstance(incident.get("prevention_summary"), str) else incident.get("prevention_summary", []),
    }

    print_report(report)


if __name__ == "__main__":
    investigate()
