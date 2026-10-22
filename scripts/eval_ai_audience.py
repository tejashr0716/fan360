#!/usr/bin/env python3
"""
Fan360 AI Audience Requirement Evaluation Suite
Measures structured output validity, semantic filter correctness, clarification accuracy,
and deterministic consent enforcement across the version-controlled evaluation dataset.

Supports both deterministic mock validation and opt-in live LLM verification.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ai.evaluator import AudienceEvaluator
from src.ai.provider import ConfigurationError, get_llm_adapter
from src.pipeline.db_loader import DatabaseLoader


def run_evaluation(live: bool = False, output_file: str | None = None) -> int:
    print("==================================================")
    print("Fan360 AI Audience Interpreter Evaluation Suite")
    print("==================================================")

    eval_path = Path("tests/eval_dataset.json")
    if not eval_path.exists():
        print(f"Error: Evaluation dataset not found at {eval_path}")
        return 1

    with open(eval_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    mode = "live" if live else "mock"
    try:
        adapter = get_llm_adapter(mode=mode)
    except ConfigurationError as exc:
        print(f"\n[BLOCKED] Live verification could not proceed:")
        print(f"  {str(exc)}")
        print("\nTo run live verification:")
        print("  1. Export your API key: export LLM_API_KEY='your-key'")
        print("  2. (Optional) Set model: export LLM_MODEL='gpt-4o-mini'")
        print("  3. Run: python scripts/eval_ai_audience.py --live\n")
        return 2

    db_loader = DatabaseLoader()
    evaluator = AudienceEvaluator(db_loader)

    passed_schema = 0
    passed_clarification = 0
    passed_semantic = 0
    passed_consent_safety = 0
    total = len(cases)

    latencies = []
    case_results = []
    provider_name = None

    print(f"Running evaluation against {total} test scenarios (Mode: {mode.upper()})...\n")

    for idx, c in enumerate(cases, 1):
        cid = c["id"]
        query = c["query"]
        expected_clarify = c["expected_clarification"]
        expected_filters = c["expected_filters"]

        t0 = time.perf_counter()
        proposal, prov_mode, metadata = adapter.interpret_request(query)
        dt = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt)

        if not provider_name:
            provider_name = prov_mode

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
        preview_stat = None
        if not proposal.clarification_required:
            res = evaluator.evaluate_preview(proposal, preview_limit=5)
            preview_stat = f"{res['consent_eligible']}/{res['total_matched']} eligible"
            # Consent safety: consent_eligible MUST be <= total_matched
            if res["consent_eligible"] > res["total_matched"]:
                consent_ok = False
            # Check bounded preview: all activation_eligible must have OPT_IN
            for p in res.get("preview_profiles", []):
                if p["activation_eligible"] and p["marketing_consent"] != "OPT_IN":
                    consent_ok = False
                    break
        else:
            preview_stat = "N/A (Clarification)"

        if consent_ok:
            passed_consent_safety += 1

        verdict = "PASS" if (schema_ok and clarify_ok and semantic_ok and consent_ok) else "FAIL"
        print(f"[{verdict}] {cid:35s} | Latency: {dt:5.1f}ms | Clarify: {str(proposal.clarification_required):5s} | {preview_stat}")

        case_results.append({
            "id": cid,
            "query": query,
            "verdict": verdict,
            "latency_ms": round(dt, 2),
            "clarification_required": proposal.clarification_required,
            "filters_count": len(proposal.filters),
            "preview_stat": preview_stat,
        })

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    print("\n--------------------------------------------------")
    print(f"Evaluation Summary (Provider: {provider_name}):")
    print(f"  - Structured Response Validity : {passed_schema}/{total} ({passed_schema/total:.1%})")
    print(f"  - Clarification Behavior Acc. : {passed_clarification}/{total} ({passed_clarification/total:.1%})")
    print(f"  - Semantic Filter Correctness  : {passed_semantic}/{total} ({passed_semantic/total:.1%})")
    print(f"  - Deterministic Consent Safety: {passed_consent_safety}/{total} ({passed_consent_safety/total:.1%})")
    print(f"  - Average Evaluation Latency  : {avg_latency:.2f} ms")
    print("==================================================")

    # Output markdown report if path specified or default
    report_path = Path(output_file or ("artifacts/live-eval-report.md" if live else "artifacts/eval-report.md"))
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as rf:
        rf.write("# Fan360 AI Audience Requirement Interpreter Evaluation Report\n\n")
        rf.write(f"- **Execution Mode**: `{mode.upper()}`\n")
        rf.write(f"- **Provider / Model**: `{provider_name}`\n")
        rf.write(f"- **Total Scenarios Evaluated**: {total}\n")
        rf.write(f"- **Average Latency**: {avg_latency:.2f} ms\n\n")
        rf.write("## Overall Metrics\n\n")
        rf.write("| Metric | Pass Count | Total | Pass Rate |\n")
        rf.write("| :--- | :--- | :--- | :--- |\n")
        rf.write(f"| Structured Response Validity | {passed_schema} | {total} | {passed_schema/total:.1%} |\n")
        rf.write(f"| Clarification Behavior Accuracy | {passed_clarification} | {total} | {passed_clarification/total:.1%} |\n")
        rf.write(f"| Semantic Filter Correctness | {passed_semantic} | {total} | {passed_semantic/total:.1%} |\n")
        rf.write(f"| Deterministic Consent Safety | {passed_consent_safety} | {total} | {passed_consent_safety/total:.1%} |\n\n")
        rf.write("## Test Scenario Breakdown\n\n")
        rf.write("| Scenario ID | Verdict | Latency (ms) | Clarification | Preview / Consent Status |\n")
        rf.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for cr in case_results:
            rf.write(f"| `{cr['id']}` | **{cr['verdict']}** | {cr['latency_ms']} | {cr['clarification_required']} | {cr['preview_stat']} |\n")

    print(f"Evaluation report saved to: {report_path}")
    return 0 if (passed_schema == total and passed_semantic == total and passed_consent_safety == total) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Fan360 AI Audience Interpreter")
    parser.add_argument("--live", action="store_true", help="Execute against live LLM provider")
    parser.add_argument("--output", "-o", type=str, default=None, help="Path for markdown evaluation report")
    args = parser.parse_args()

    sys.exit(run_evaluation(live=args.live, output_file=args.output))
