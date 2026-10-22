# Testing, Quality & Benchmarking Guide
## Fan360 Verification Framework

---

## 1. Automated Test Suite (17 Tests)

The test suite validates correctness across 12 requirement areas using `pytest`.

Run all tests:
```bash
.venv/bin/pytest -v
```

Generate JUnit XML results:
```bash
.venv/bin/pytest --junitxml=artifacts/test-results.xml tests/
```

### Test Coverage by Acceptance Area

| # | Acceptance Requirement | Test Module | Verification Method |
| :--- | :--- | :--- | :--- |
| **1** | Fixture Transformation | `tests/test_segments.py` | Runs PySpark pipeline on 10-fan fixture; verifies row schema and types. |
| **2** | Exact Expected Memberships | `tests/test_segments.py` | Compares computed segment qualifications against hand-authored `expected_memberships.json` (0 mismatches). |
| **3** | Threshold & Window Boundaries | `tests/test_validation.py` & `tests/test_segments.py` | Tests timestamps on exact boundary vs 1 second future; tests spend of $249.99 vs $250.00. |
| **4** | Duplicate Handling | `tests/test_validation.py` | Tests duplicate event IDs; verifies deduplication count without dropping unique events. |
| **5** | Quarantine Reason Codes | `tests/test_validation.py` | Compares quarantined items and reason codes against `expected_quarantine.json`. |
| **6** | Consent Eligibility | `tests/test_consent.py` | Asserts non-consenting fans (`OPT_OUT`, `NONE`) are excluded from activation exports. |
| **7** | Consent Withdrawal | `tests/test_consent.py` | Injects an opt-out update into a previously consenting fan; confirms immediate removal from activation on re-run. |
| **8** | Idempotent Reruns | `tests/test_idempotency.py` | Executes pipeline twice on same inputs; compares row counts and canonical SHA256 hashes of business records. |
| **9** | Profile & Spend Aggregation | `tests/test_segments.py` | Asserts exact sum of completed orders and order counts for active and non-buyer fans. |
| **10** | API Pagination & Errors | `tests/test_api.py` | Tests `limit` and `offset`, page size bounds (`limit > 100` returns 422), and 404 on missing fan/segment. |
| **11** | Database Integration | `tests/test_idempotency.py` | Tests PostgreSQL schema initialization, table creation, and conflict handling. |
| **12** | End-to-End Pipeline Run | `tests/test_e2e.py` | Generates synthetic data, executes ingestion, PySpark processing, PostgreSQL persistence, and API query validation. |

---

## 2. Automated Benchmarking & Evidence Execution

Run the complete benchmark and audit suite:
```bash
.venv/bin/python scripts/run_benchmarks.py
```

This executable script produces 5 machine-readable evidence files in `artifacts/`:
1. `artifacts/metrics.json`: Complete quantitative dump with git commit, hardware specs, volumes, reconciliation status, quality metrics, and latency numbers.
2. `artifacts/test-results.xml`: Standard JUnit XML report containing outcomes of automated tests.
3. `artifacts/benchmark-results.json`: Pipeline throughput and API latency distributions.
4. `artifacts/benchmark-report.md`: Markdown summary of execution performance with honest baseline comparison.
5. `artifacts/data-quality-report.md`: Reconciliation balance breakdown and per-category detection precision & recall against ground truth.
6. `artifacts/resume-evidence.md`: Direct mapping between measured numbers and XYZ résumé achievements.

---

## 3. Interpreting Benchmark Results

### PySpark vs Python Baseline Comparison
- **Python In-Memory Baseline**: ~0.10s on 110k rows.
- **PySpark Local Engine**: ~4.6s median on 110k rows.
- **Engineering Note**: On small datasets (<1 million rows), a local PySpark job has JVM startup and Catalyst query compilation overhead. PySpark's architecture is selected for distributed scalability across clusters when fan event streams exceed single-node memory.
