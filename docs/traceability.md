# Requirement-to-Test Traceability Matrix
## Fan360 Verification & Test Coverage Mapping

> **Methodology & Integrity Standard**: In accordance with rigorous software engineering practice, passing schema-validation tests are **not** presented as proof of semantic interpretation accuracy or consent enforcement. 
> 
> Verification types are strictly distinguished between:
> 1. **Unit & Property Tests** (Pydantic schema validation, regex boundaries, error handling)
> 2. **Mock Provider Tests** (Deterministic local heuristics)
> 3. **Database Integration Tests** (PostgreSQL SQL queries, transaction boundaries, idempotency)
> 4. **Live Provider Evaluations** (Real-world LLM calls against external Groq/OpenAI endpoints)
> 5. **Interactive UI Verification** (Streamlit dashboard walkthrough)

---

## 1. Traceability Matrix

| Req ID | Requirement Description | Implementing File & Function | Verification Method & Test Name | Verification Status | Known Limitations / Boundaries |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-001** | Unified Customer Profile | `src/pipeline/spark_pipeline.py`<br>`SparkFanPipeline.process()` | `tests/test_segments.py`<br>`test_spend_and_order_count_aggregation` | **Verified by automated test** | Batch calculation; daily refresh cadence. |
| **REQ-002** | Hierarchical Validation & Quarantine | `src/pipeline/validation.py`<br>`DataValidator.validate_dataset()` | `tests/test_validation.py`<br>`test_fixture_validation_and_reconciliation` | **Verified by automated test** | Evaluated on raw CSV inputs; 5 hierarchical reason codes. |
| **REQ-003** | Latest-Effective Consent Resolution | `src/pipeline/spark_pipeline.py`<br>`_resolve_consent()` | `tests/test_consent.py`<br>`test_consent_latest_effective_and_withdrawal` | **Verified by automated test** | Windowed `row_number()` by timestamp descending with event_id tiebreaker. |
| **REQ-004** | Idempotent Storage & Pipeline Audit | `src/pipeline/db_loader.py`<br>`DatabaseLoader.upsert_fan_profiles()` | `tests/test_idempotency.py`<br>`test_idempotent_pipeline_execution` | **Verified by automated test** | Single-node PostgreSQL target; requires primary key integrity. |
| **REQ-005** | Distributed PySpark Aggregations | `src/pipeline/spark_pipeline.py`<br>`_aggregate_fan_metrics()` | `tests/test_e2e.py`<br>`test_full_end_to_end_pipeline_and_api` | **Verified by automated test** | Executed in local Spark master mode (`local[*]`). |
| **REQ-006** | Documented Cohort Segmentation | `src/pipeline/segmentation.py`<br>`SegmentEngine.evaluate_all()` | `tests/test_segments.py`<br>`test_segment_exact_matches_fixture` | **Verified by automated test** | 5 predefined cohorts defined in `config/segment_rules.yaml`. |
| **REQ-007** | REST API & Dashboard | `src/api/app.py`<br>`src/ui/dashboard.py` | `tests/test_api.py`<br>`test_segments_list_endpoint` | **Verified by automated test & manual UI** | Interactive Streamlit UI runs locally on port 8501. |
| **REQ-008** | Natural-Language Requirement Translation | `src/ai/provider.py`<br>`LiveLLMProvider.interpret_request()` | `scripts/eval_ai_audience.py`<br>`TC_01_SIMPLE_COUNTRY` to `TC_10` | **Verified by live evaluation (Groq)** | Output bounded by `ProposedSegment` JSON schema. |
| **REQ-009** | Strict Allowlisted Attribute Validation | `src/ai/schema.py`<br>`SegmentFilter.validate_field()` | `tests/test_ai_audience.py`<br>`test_reject_unknown_field` | **Verified by automated test** | Rejects attributes not explicitly in `ALLOWLISTED_FIELDS`. |
| **REQ-010** | Conjunctive-Only Logic (AND, Max 5) | `src/ai/schema.py`<br>`ProposedSegment` (max_length=5) | `tests/test_ai_audience.py`<br>`test_reject_excessive_filters` | **Verified by automated test** | Disjunctive (OR) requires splitting into multiple segments. |
| **REQ-011** | Ambiguity & Undefined Threshold Triage | `src/ai/provider.py`<br>`MockLLMProvider` / `SYSTEM_PROMPT` | `tests/test_ai_audience.py`<br>`test_mock_provider_ambiguous_term_clarification` | **Verified by automated test & live eval** | Prompt instructions mandate clarification on undefined terms. |
| **REQ-012** | Input Validation & Length Boundaries | `src/ai/schema.py`<br>`SegmentFilter` validators | `tests/test_ai_audience.py`<br>`test_reject_non_finite_numbers` | **Verified by automated test** | Rejects NaN, Inf, negative order counts, spend > $10M. |
| **REQ-013** | Zero Customer Data Transmission | `src/ai/provider.py`<br>`SYSTEM_PROMPT` construction | Manual Inspection & Payload Audit | **Verified manually** | Only schema metadata and user prompt sent; zero PII. |
| **REQ-014** | Two-Stage Human Review Interface | `src/ui/dashboard.py`<br>`tab5` Streamlit form | Manual UI Verification | **Verified manually** | Visual display of proposed filters before preview trigger. |
| **REQ-015** | Preview-Time Payload Revalidation | `src/api/app.py`<br>`preview_audience()` endpoint | `tests/test_ai_audience.py`<br>`test_preview_revalidates_tampered_payload` | **Verified by automated test** | Pydantic revalidation prevents client-side tampering. |
| **REQ-016** | Inert SQL Parameterization | `src/ai/evaluator.py`<br>`AudienceEvaluator._build_query()` | `tests/test_ai_audience.py`<br>`test_evaluator_parameterized_sql_safety` | **Verified by automated test** | Uses psycopg2 `%s` parameterized tuples for all values. |
| **REQ-017** | Mandatory Consent Segregation | `src/ai/evaluator.py`<br>`AudienceEvaluator.evaluate_preview()` | `tests/test_ai_audience.py`<br>`test_mandatory_consent_segregation` | **Verified by automated test & live eval** | Mandatory SQL filter `marketing_consent_status = 'OPT_IN'`. |
| **REQ-018** | Explicit Mode (Zero Silent Fallback) | `src/ai/provider.py`<br>`get_llm_adapter()` factory | `tests/test_ai_audience.py`<br>`test_explicit_mode_factory` | **Verified by automated test** | Fails fast with `ConfigurationError` if key missing in live mode. |
| **REQ-019** | Bounded Retries & Error Taxonomy | `src/ai/provider.py`<br>`LiveLLMProvider._execute_http_post()` | `tests/test_ai_audience.py`<br>`test_live_provider_http_401_auth_error`, etc. | **Verified by automated test** | 10 mocked HTTP regression tests (401, 429, 503 retry, etc.). |
| **REQ-020** | Automated Traceability & Evaluation Suite | `scripts/eval_ai_audience.py`<br>`tests/eval_dataset.json` | `artifacts/live-eval-report.md` | **Verified by live evaluation (Groq)** | 10 frozen cases executed with 100% pass rate. |

---

## 2. Test Execution Summary

### Automated Pytest Suite
```text
Total Test Cases: 42
Passed: 42 (100%)
Failed: 0
Skipped: 0
Execution Time: 26.47s
Coverage Areas: Data Generator, Validator & Quarantine, PySpark Transformations,
                PostgreSQL Idempotency, Consent Engine, FastAPI Endpoints,
                AI Schema Validation, Provider Error Regression, Consent Segregation.
```

### Frozen Evaluation Benchmark (Live Mode)
```text
Execution Provider: Live Model (openai/gpt-oss-120b) via Groq Cloud
Total Scenarios: 10
Passed Scenarios: 10 (100%)
Average Latency: 977.56 ms
Evidence Artifact: artifacts/live-eval-report.md
Commit SHA: d968d0b
```
