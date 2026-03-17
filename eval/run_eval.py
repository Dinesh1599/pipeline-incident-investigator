"""
run_eval.py — Evaluation framework runner.

Loads scenario definitions from eval/scenarios/, runs each through
the agent graph, and scores the output against expected results.

Blueprint reference: Section 16 (Agent Evaluation Framework)

Usage:
    python eval/run_eval.py                          # Run all scenarios
    python eval/run_eval.py --scenario tc001         # Run one scenario
    python eval/run_eval.py --skip-run --results evaluation_results.json  # Score existing results
"""

import json
import logging
import os
import sys
from pathlib import Path

import click

from dotenv import load_dotenv
load_dotenv(".env.local")

from eval.scoring import score_scenario

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def load_scenarios(scenario_filter: str | None = None) -> list[dict]:
    """Load scenario definitions from JSON files."""
    scenarios = []
    for f in sorted(SCENARIOS_DIR.glob("*.json")):
        with open(f) as fh:
            scenario = json.load(fh)

        if scenario_filter and scenario_filter not in f.stem:
            continue

        scenarios.append(scenario)

    return scenarios


def run_scenario(scenario: dict) -> dict:
    """Run a single scenario through the agent graph."""
    from agent.graph import compile_graph

    trigger = scenario["trigger"]

    # Skip if run_id placeholder not updated (for failure scenarios)
    if "UPDATE" in trigger.get("run_id", ""):
        logger.warning(
            "  SKIPPED %s — update run_id in %s",
            scenario["scenario_id"],
            f"eval/scenarios/tc{scenario['scenario_id'][-3:]}_*.json",
        )
        return {}

    app = compile_graph()
    result = app.invoke(trigger)
    return result.get("final_report", {})


@click.command()
@click.option("--scenario", "-s", default=None, help="Run specific scenario (e.g., tc001)")
@click.option("--skip-run", is_flag=True, help="Skip running, just score existing results")
@click.option("--results", "-r", default=None, help="Path to existing results JSON")
@click.option("--output", "-o", default="evaluation_results.json", help="Output file")
def main(scenario, skip_run, results, output):
    """Run evaluation scenarios and score the results."""

    print("=" * 70)
    print("PIPELINE INCIDENT INVESTIGATOR — EVALUATION")
    print("=" * 70)

    scenarios = load_scenarios(scenario)
    if not scenarios:
        logger.error("No scenarios found in eval/scenarios/")
        sys.exit(1)

    logger.info("Loaded %d scenario(s)\n", len(scenarios))

    all_reports = {}
    all_scores = {}

    if skip_run and results:
        # Load existing results
        with open(results) as f:
            data = json.load(f)
        all_reports = data.get("results", {})
    else:
        # Run each scenario
        for scen in scenarios:
            name = scen["scenario_name"]
            sid = scen["scenario_id"]

            print(f"\n{'─' * 70}")
            print(f"SCENARIO: {sid} — {name}")
            print(f"{'─' * 70}")

            report = run_scenario(scen)
            if report:
                all_reports[name] = report

                # Print summary
                print(f"\n  Class:      {report.get('failure_class')}")
                print(f"  Confidence: {report.get('confidence')}")
                print(f"  Root cause: {report.get('root_cause', '')[:120]}")
                fix = report.get("fix", {})
                print(f"  Fix:        {fix.get('immediate', '')[:120]}")

    # Score all results
    for scen in scenarios:
        name = scen["scenario_name"]
        if name in all_reports:
            all_scores[name] = score_scenario(all_reports[name], scen["expected"])

    # Print scorecard
    print(f"\n{'=' * 70}")
    print("SCORECARD")
    print(f"{'=' * 70}")

    for name, scores in all_scores.items():
        print(f"\n  {name}:")
        for criterion, value in scores.items():
            if criterion != "total":
                if value >= 1.0:
                    status = "[PASS]"
                elif value >= 0.5:
                    status = "[PARTIAL]"
                else:
                    status = "[FAIL]"
                print(f"    {status:10s} {criterion}: {value}")
        print(f"    {'':10s} TOTAL: {scores['total']}/6.0")

    if all_scores:
        overall = sum(s["total"] for s in all_scores.values()) / len(all_scores)
        print(f"\n  Overall average: {overall:.1f}/6.0")

        if overall >= 5.0:
            print("  EXCELLENT")
        elif overall >= 4.0:
            print("  GOOD")
        elif overall >= 3.0:
            print("  FAIR")
        else:
            print("  NEEDS WORK")

    # Save results
    with open(output, "w") as f:
        json.dump(
            {"results": all_reports, "scores": all_scores},
            f,
            indent=2,
            default=str,
        )
    print(f"\n  Results saved to {output}")


if __name__ == "__main__":
    main()
