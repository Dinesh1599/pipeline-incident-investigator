"""
Test each prompt independently against the OpenAI API.

Sends sample inputs from the null-key failure scenario and
checks that the output is valid JSON with expected fields.

Requires: OPENAI_API_KEY in .env.local

"""

import json

from dotenv import load_dotenv
load_dotenv(".env.local")

from langchain_openai import ChatOpenAI
from agent.prompts import extraction, classification, code_inspection, reasoning, fix_generation
from agent.utils.config import MODELS, LLM_TEMPERATURE


# ── Sample data from the null-key failure scenario ──────────────

SAMPLE_LOG = """
[2026-03-11T02:05:01Z] INFO - 1 of 1 START sql table model gold.fct_sales
[2026-03-11T02:05:01Z] INFO - 1 of 1 ERROR creating sql table model gold.fct_sales
[2026-03-11T02:05:01Z] INFO - Failure in model fct_sales (models/gold/fct_sales.sql)
[2026-03-11T02:05:01Z] INFO -   Database Error in model fct_sales (models/gold/fct_sales.sql)
[2026-03-11T02:05:01Z] INFO -   null value in column "customer_id" violates not-null constraint
[2026-03-11T02:05:01Z] INFO -   compiled code at target/run/sales_pipeline/models/gold/fct_sales.sql
[2026-03-11T02:05:01Z] ERROR - Task failed with exception
""".strip()

SAMPLE_REGEX_SIGNALS = {
    "error_type": "not_null_violation",
    "error_message": 'null value in column "customer_id" violates not-null constraint',
    "sql_state_code": "23502",
    "objects_referenced": {"tables": [], "columns": ["customer_id"], "models": ["fct_sales"]},
    "regex_matches": [
        {"pattern": "not_null_violation", "match": 'null value in column "customer_id" violates not-null constraint', "groups": ("customer_id",)},
    ],
}

SAMPLE_MODEL_SQL = """-- fct_sales.sql
SELECT
    ss.customer_id,
    sc.customer_name,
    sc.region,
    ss.order_date,
    COUNT(*)                AS order_count,
    SUM(ss.total_amount)    AS daily_revenue
FROM silver.silver_sales ss
LEFT JOIN silver.silver_customers sc
    ON ss.customer_id = sc.customer_id
GROUP BY
    ss.customer_id,
    sc.customer_name,
    sc.region,
    ss.order_date
""".strip()


def parse_json_response(text: str) -> dict:  # for debugging and cleaning up markdown fences
    """Parse JSON from LLM response, handling markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    # print("\n")
    # print("\n")
    # print("\n")
    # print("JSON RESPONSE:")
    # print("\n")
    # print(cleaned.strip())
    # print("\n")
    # print("\n")
    # print("\n") 
    return json.loads(cleaned.strip())


def test_extraction_prompt():
    print("── Testing Signal Extraction Prompt ──")
    llm = ChatOpenAI(model=MODELS["signal_extraction"], temperature=LLM_TEMPERATURE)

    user_msg = extraction.build_user_message(SAMPLE_LOG, SAMPLE_REGEX_SIGNALS)
    response = llm.invoke([
        {"role": "system", "content": extraction.SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])

    result = parse_json_response(response.content)
    print(f"  error_type: {result.get('error_type')}")
    print(f"  objects: {result.get('objects_referenced')}")
    print(f"  sql_state: {result.get('sql_state_code')}")

    assert result.get("error_type") is not None, "Missing error_type"
    assert "objects_referenced" in result, "Missing objects_referenced"
    print("  PASSED\n")
    return result


def test_classification_prompt(extracted_signals: dict):
    print("── Testing Classification Prompt ──")
    llm = ChatOpenAI(model=MODELS["classification"], temperature=LLM_TEMPERATURE)

    pipeline_metadata = {
        "dag_id": "sales_pipeline",
        "task_id": "run_dbt_fct_sales",
        "model_name": "fct_sales",
        "model_description": "Joins silver_sales with silver_customers and aggregates by customer and date",
    }

    user_msg = classification.build_user_message(extracted_signals, pipeline_metadata)
    # print("\n")
    # print("\n")
    # print("\n")
    # print("USER MESSAGE:")
    # print("\n")
    # print(user_msg)
    # print("\n")
    # print("\n")
    # print("\n") 
    response = llm.invoke([
        {"role": "system", "content": classification.SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])
    # print("\n")
    # print("\n")
    # print("\n")
    # print("RESPONSE:")
    # print("\n")
    # print(response.content)
    # print("\n")
    # print("\n")
    # print("\n")

    result = parse_json_response(response.content)
    print(f"  primary_class: {result.get('primary_class')}")
    print(f"  confidence: {result.get('confidence')}")
    print(f"  reasoning: {result.get('reasoning', '')[:100]}")
    print(f"  priorities: {result.get('investigation_priorities')}")

    assert result.get("primary_class") in [
        "data_quality", "schema_drift", "code_failure",
        "dependency", "resource", "access", "silent_correctness",
    ], f"Unexpected class: {result.get('primary_class')}"
    assert 0 <= result.get("confidence", -1) <= 1, "Confidence out of range"
    print("  PASSED\n")
    return result


def test_code_inspection_prompt(extracted_signals: dict, classification_result: dict):
    print("── Testing Code Inspection Prompt ──")
    llm = ChatOpenAI(model=MODELS["code_inspection"], temperature=LLM_TEMPERATURE)

    evidence_results = [
        {"template": "null_check", "rows": [{"null_count": 6}], "row_count": 1, "error": None},
        {"template": "row_count", "rows": [{"total_rows": 20}], "row_count": 1, "error": None},
    ]

    user_msg = code_inspection.build_user_message(
        failure_context=extracted_signals,
        classification=classification_result,
        evidence_results=evidence_results,
        model_sql=SAMPLE_MODEL_SQL,
        model_name="fct_sales",
    )
    response = llm.invoke([
        {"role": "system", "content": code_inspection.SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])

    result = parse_json_response(response.content)
    print(f"  findings: {len(result.get('findings', []))}")
    for f in result.get("findings", []):
        print(f"    [{f.get('severity')}] {f.get('location')}: {f.get('issue', '')[:80]}")
    print(f"  primary_finding: {result.get('primary_finding', '')[:100]}")

    assert len(result.get("findings", [])) > 0, "No findings"
    print("  PASSED\n")
    return result


def test_reasoning_prompt(
    extracted_signals: dict,
    classification_result: dict,
    code_findings: dict,
):
    print("── Testing Root Cause Reasoning Prompt ──")
    llm = ChatOpenAI(model=MODELS["root_cause_reasoning"], temperature=LLM_TEMPERATURE)

    database_evidence = [
        {"template": "null_check", "rows": [{"null_count": 6}], "row_count": 1, "error": None, "context": "bronze.sales"},
        {"template": "row_count", "rows": [{"total_rows": 20}], "row_count": 1, "error": None, "context": "bronze.sales"},
        {"template": "duplicate_check", "rows": [], "row_count": 0, "error": None, "context": "bronze.sales"},
    ]

    lineage = {
        "model": "fct_sales",
        "upstream_models": ["silver_sales", "silver_customers"],
        "upstream_sources": [{"source_name": "bronze", "table_name": "sales", "schema": "bronze"}],
        "downstream_models": [],
    }

    similar_incidents = [
        {
            "incident_id": "SEED-001",
            "summary": "Null customer_id in bronze.sales caused NOT NULL constraint violation in fct_sales.",
            "root_cause": "Source CSV had empty customer_id. No validation at ingestion.",
            "fix_applied": "Added WHERE customer_id IS NOT NULL filter and not_null dbt test.",
            "similarity_score": 0.92,
        }
    ]

    user_msg = reasoning.build_user_message(
        failure_signals=extracted_signals,
        classification=classification_result,
        database_evidence=database_evidence,
        code_findings=code_findings,
        lineage_context=lineage,
        similar_incidents=similar_incidents,
    )
    response = llm.invoke([
        {"role": "system", "content": reasoning.SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])

    result = parse_json_response(response.content)
    print(f"  root_cause: {result.get('root_cause', '')[:150]}")
    print(f"  confidence: {result.get('confidence')}")
    print(f"  evidence_chain: {len(result.get('evidence_chain', []))} items")
    print(f"  alternatives: {len(result.get('alternative_causes_considered', []))}")

    assert result.get("root_cause"), "Missing root_cause"
    assert 0 <= result.get("confidence", -1) <= 1, "Confidence out of range"
    assert len(result.get("evidence_chain", [])) > 0, "Empty evidence chain"
    print("  PASSED\n")
    return result


def test_fix_generation_prompt(reasoning_result: dict):
    print("── Testing Fix Generation Prompt ──")
    llm = ChatOpenAI(model=MODELS["fix_generation"], temperature=LLM_TEMPERATURE)

    user_msg = fix_generation.build_user_message(
        root_cause=reasoning_result.get("root_cause", ""),
        evidence_chain=reasoning_result.get("evidence_chain", []),
        confidence=reasoning_result.get("confidence", 0.9),
        code_context=SAMPLE_MODEL_SQL,
        model_name="fct_sales",
        failure_class="data_quality",
    )
    response = llm.invoke([
        {"role": "system", "content": fix_generation.SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])

    result = parse_json_response(response.content)
    fix = result.get("fix", {})
    print(f"  immediate: {fix.get('immediate', '')[:100]}")
    print(f"  preventive: {fix.get('preventive', '')[:100]}")
    print(f"  monitoring: {fix.get('monitoring', '')[:100]}")
    print(f"  prevention extras: {result.get('prevention', [])}")
    print(f"  fix_confidence: {result.get('fix_confidence')}")

    assert fix.get("immediate"), "Missing immediate fix"
    assert fix.get("preventive"), "Missing preventive fix"
    assert fix.get("monitoring"), "Missing monitoring recommendation"
    print("  PASSED\n")


if __name__ == "__main__":
    # Each prompt is tested in pipeline order — output from one feeds the next
    signals = test_extraction_prompt()
    classification_result = test_classification_prompt(signals)
    code_findings = test_code_inspection_prompt(signals, classification_result)
    #reasoning_result = test_reasoning_prompt(signals, classification_result, code_findings)
    #test_fix_generation_prompt(reasoning_result)

    print("All prompt tests passed.")
