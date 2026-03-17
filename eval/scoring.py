"""
scoring.py — Evaluation scoring rubric.

Scores agent output against expected results using the
6-point rubric

Criteria (1.0 each, 6.0 total):
    1. Classification correct
    2. Table/model identified
    3. Column identified
    4. Root cause accurate
    5. Fix is actionable
    6. Prevention is reasonable
"""


def score_scenario(report: dict, expected: dict) -> dict:
    """Score a single scenario against expected output.

    Args:
        report: The agent's final_report output.
        expected: The expected output from the scenario JSON.

    Returns:
        Dict with individual scores and total.
    """
    scores = {}

    # Collect all text for searching
    root_cause = report.get("root_cause", "").lower()
    evidence_text = " ".join(report.get("evidence_chain", [])).lower()
    fix = report.get("fix", {})
    fix_text = f"{fix.get('immediate', '')} {fix.get('preventive', '')} {fix.get('monitoring', '')}".lower()
    prevention_text = " ".join(report.get("prevention", [])).lower()
    all_text = f"{root_cause} {evidence_text} {fix_text} {prevention_text}"

    # 1. Classification correct (1.0)
    expected_class = expected.get("failure_class", "")
    actual_class = report.get("failure_class", "")
    if actual_class == expected_class:
        scores["classification"] = 1.0
    elif actual_class in ("data_quality", "dependency") and expected_class == "silent_correctness":
        scores["classification"] = 0.5
    else:
        scores["classification"] = 0.0

    # 2. Table/model identified (1.0)
    expected_tables = expected.get("expected_tables", [])
    table_found = any(t.lower() in all_text for t in expected_tables)
    scores["table_identified"] = 1.0 if table_found else 0.0

    # 3. Column identified (1.0)
    expected_col = expected.get("expected_column", "")
    if expected_col:
        col_found = expected_col.lower() in all_text
        scores["column_identified"] = 1.0 if col_found else 0.0
    else:
        scores["column_identified"] = 1.0

    # 4. Root cause accurate (1.0)
    keywords = expected.get("root_cause_keywords", [])
    if keywords:
        found = sum(1 for kw in keywords if kw.lower() in root_cause)
        ratio = found / len(keywords)
        if ratio >= 0.4:
            scores["root_cause"] = 1.0
        elif ratio >= 0.2:
            scores["root_cause"] = 0.5
        else:
            scores["root_cause"] = 0.0
    else:
        scores["root_cause"] = 1.0

    # 5. Fix is actionable (1.0)
    fix_keywords = expected.get("fix_should_mention", [])
    if fix_keywords:
        found = sum(1 for kw in fix_keywords if kw.lower() in fix_text)
        if found >= 2:
            scores["fix_actionable"] = 1.0
        elif found >= 1:
            scores["fix_actionable"] = 0.5
        else:
            scores["fix_actionable"] = 0.0
    else:
        scores["fix_actionable"] = 1.0

    # 6. Prevention is reasonable (1.0)
    prev_keywords = expected.get("prevention_should_mention", [])
    combined_prev = f"{fix_text} {prevention_text}"
    if prev_keywords:
        found = sum(1 for kw in prev_keywords if kw.lower() in combined_prev)
        if found >= 2:
            scores["prevention"] = 1.0
        elif found >= 1:
            scores["prevention"] = 0.5
        else:
            scores["prevention"] = 0.0
    else:
        scores["prevention"] = 1.0

    scores["total"] = sum(scores.values())
    return scores
