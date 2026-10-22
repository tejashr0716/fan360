#!/usr/bin/env python3
"""
Fan360 AI Audience Requirement Evaluation Suite
Measures structured output validity, semantic filter correctness, clarification accuracy,
and deterministic consent enforcement across the version-controlled evaluation dataset.
"""

import json
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ai.evaluator import AudienceEvaluator
from src.ai.provider import get_llm_adapter
from src.pipeline.db_loader import DatabaseLoader


def run_evaluation():
    print("==================================================")
    print("Fan360 AI Audience Interpreter Evaluation Suite")
    print("==================================================")

    eval_path = Path("tests/eval_dataset.json")
    if not eval_path.exists():
        print(f"Error: Evaluation dataset not found at {eval_path}")
        sys.exit(1)

    with open(eval_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    adapter = get_llm_adapter()
    db_loader = DatabaseLoader()
    evaluator = AudienceEvaluator(db_loader)

    passed_schema = 0
    passed_clarification = 0
    passed_semantic = 0
    passed_consent_safety = 0
    total = len(cases)

    provider_name = None

    print(f"Running evaluation against {total} test scenarios...\n")

    for idx, c in enumerate(cases, 1):
        cid = c["id"]
        query = c["query"]
        expected_clarify = c["expected_clarification"]
        expected_filters = c["expected_filters"]

        t0 = time.perf_counter()
        proposal, mode = adapter.interpret_request(query)
        dt = (time.perf_counter() - t0) * 1000.0

        if not provider_name:
            provider_name = mode

        # 1. Schema Validity
        schema_ok = True
        try:
            proposal.model_dump()
            passed_schema += 1
        except Exception:
            schema_ok = False

        # 2. Clarification Accuracy
        clarify_ok = (proposal.clarification_required == expected_clarify)
        if clarify_ok:
            passed_clarification += 1

        # 3. Semantic Correctness (Field & Operator matches)
        semantic_ok = True
        if not expected_clarify:
            if len(proposal.filters) != len(expected_filters):
                semantic_ok = False
            else:
                for exp_f in expected_filters:
                    match_found = any(
                        pf.field == exp_f["field"] and pf.operator == exp_f["operator"]
                        for pf in proposal.filters
                    )
                    if not match_found:
                        semantic_ok = False
                        break
        else:
            semantic_ok = clarify_ok

        if semantic_ok:
            passed_semantic += 1

        # 4. Consent Enforcement Preview Check
        consent_ok = True
        if not proposal.clarification_required:
            res = evaluator.evaluate_preview(proposal, preview_limit=5)
            # Consent safety: consent_eligible MUST be <= total_matched
            if res["consent_eligible"] > res["total_matched"]:
                consent_ok = False
            # Check bounded preview: all activation_eligible must have OPT_IN
            for p in res.get("preview_profiles", []):
                if p["activation_eligible"] and p["marketing_consent"] != "OPT_IN":
                    consent_ok = False
                    break
        if consent_ok:
            passed_consent_safety += 1

        verdict = "PASS" if (schema_ok and clarify_ok and semantic_ok and consent_ok) else "FAIL"
        print(f"[{verdict}] {cid:35s} | Latency: {dt:5.1f}ms | Clarify: {str(proposal.clarification_required):5s} | Mode: {mode}")

    print("\n--------------------------------------------------")
    print(f"Evaluation Summary (Provider: {provider_name}):")
    print(f"  - Structured Response Validity : {passed_schema}/{total} ({passed_schema/total:.1%})")
    print(f"  - Clarification Behavior Acc. : {passed_clarification}/{total} ({passed_clarification/total:.1%})")
    print(f"  - Semantic Filter Correctness  : {passed_semantic}/{total} ({passed_semantic/total:.1%})")
    print(f"  - Deterministic Consent Safety: {passed_consent_safety}/{total} ({passed_consent_safety/total:.1%})")
    print("==================================================")


if __name__ == "__main__":
    run_evaluation()
