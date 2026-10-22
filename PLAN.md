# Fan360 Implementation Plan & Acceptance Tracking

## Overview
Fan360 is an educational motorsport fan data and audience segmentation platform. This plan tracks the phased architecture, implementation milestones, and automated verification steps executed to produce verified, reproducible résumé achievements in the Google XYZ format: “Accomplished [X], measured by [Y], by doing [Z].”

## Architecture & Technology Stack
- **Language**: Python 3.14 (pinned in local `.venv`)
- **Transformations**: PySpark 4.2.0 (local engine running on OpenJDK 25)
- **Database**: PostgreSQL 16 (running on port 5432, with automated schema creation)
- **API**: FastAPI + Uvicorn + Pydantic v2
- **UI**: Streamlit
- **Testing**: pytest (17 passed automated tests), JUnit XML output
- **Benchmarking & Quality**: Custom deterministic audit scripts generating machine-readable evidence (`artifacts/`)

## Milestone Roadmap & Status

### Milestone 1: Environment & Project Foundation
- [x] Verify local runtime: Python 3.14.6, OpenJDK 25.0.4, PostgreSQL 16.15, Git.
- [x] Pin dependencies in `requirements.txt` and install in `.venv`.
- [x] Create project layout, directories, and base configuration (`config/config.yaml`, `config/segment_rules.yaml`).
- [x] Write `PLAN.md`.
- *Acceptance Criteria*: Virtual environment active, PySpark and PostgreSQL connections verified. [PASSED]

### Milestone 2: Synthetic Data Generator & Deterministic Fixtures
- [x] Implement `src/generator/synthetic_data.py`:
  - Fictional motorsport context (Apex Velocity Racing, fictional drivers: Elena Vance, Marcus Lindholm, Sofia Al-Mansoor, Lucas Rossi).
  - Generator manifest tracking seed, intended counts, and injected defect categories.
  - Injected defects: duplicate IDs, missing required fields, invalid timestamps, orphan fans, negative amounts, conflicting consent updates.
- [x] Create small hand-authored golden test fixtures (`tests/fixtures/`) with 100% human-verified ground truth.
- [x] Implement CLI generator command (`scripts/generate_data.py`) with configurable volume, seed, error rates, and fixed "as of" timestamp.
- *Acceptance Criteria*: Generator creates reconcilable raw data and manifest; fixtures match strict schema. [PASSED]

### Milestone 3: Data Quality, Quarantine & PySpark Pipeline
- [x] Implement data quality engine (`src/pipeline/validation.py`):
  - Field-level & schema validation with unambiguous reason codes.
  - Non-double-counting quarantine logic.
  - Deterministic deduplication.
- [x] Implement PySpark ETL and enrichment pipeline (`src/pipeline/spark_pipeline.py`):
  - Ingest raw sources.
  - Build consolidated fan profiles (last activity, valid completed order count, total valid spend in USD, latest resolved marketing consent).
  - Calculate audience segments based on `config/segment_rules.yaml`.
  - Documented cart-abandonment matching session/cart and purchase resolution.
  - Separation of descriptive segment qualification vs. consent-based activation eligibility.
  - Per-membership explanation reason payloads.
- [x] Implement database loading & idempotent storage (`src/pipeline/db_loader.py`):
  - PostgreSQL tables for profiles, events, consents, segments, memberships, quarantines, and run audit.
  - Idempotent upsert logic with stable primary keys (`ON CONFLICT DO UPDATE`).
- *Acceptance Criteria*: End-to-end pipeline executes on fixtures and full dataset; audit report reconciles raw, accepted, deduplicated, and quarantined counts with 100% mathematical balance. [PASSED]

### Milestone 4: FastAPI REST API & Streamlit Dashboard
- [x] Implement FastAPI application (`src/api/app.py`):
  - `GET /health`
  - `GET /fans/{fan_id}`
  - `GET /segments`
  - `GET /segments/{segment_name}/members` (with pagination, activation-only filter, and reasons)
  - `GET /runs/{run_id}/quality`
- [x] Implement Streamlit dashboard (`src/ui/dashboard.py`):
  - Run & reconciliation summary.
  - Data quality & quarantine explorer.
  - Fan profile search & activity timeline.
  - Segment membership reasons & consent-filtered activation audience preview.
- *Acceptance Criteria*: All API endpoints return valid JSON matching schemas; Streamlit UI renders without exceptions. [PASSED]

### Milestone 5: Automated Testing Suite
- [x] Implement comprehensive test suite (`tests/`):
  1. Small known fixture transformation (`test_segments.py`)
  2. Exact hand-authored segment memberships comparison (`test_segments.py`)
  3. Threshold and time-window boundary conditions (`test_validation.py`, `test_segments.py`)
  4. Duplicate handling (`test_validation.py`)
  5. Quarantine reason code assignment (`test_validation.py`)
  6. Consent eligibility filtering (`test_consent.py`)
  7. Consent withdrawal reflection (`test_consent.py`)
  8. Idempotent rerun verification with SHA256 canonical output hashes (`test_idempotency.py`)
  9. Fan profile spend & order count aggregations (`test_segments.py`)
  10. API pagination, validation, and error handling (`test_api.py`)
  11. Database integration tests (`test_idempotency.py`)
  12. Complete end-to-end pipeline run test (`test_e2e.py`)
- *Acceptance Criteria*: `pytest` runs and passes 17 of 17 tests (100%), outputs `artifacts/test-results.xml`. [PASSED]

### Milestone 6: Measurement, Benchmarking & Evidence Generation
- [x] Implement benchmarking and quality audit runner (`scripts/run_benchmarks.py`):
  - Measure detection precision and recall against labeled synthetic defects.
  - Verify idempotency across consecutive runs.
  - Measure API response latency (p50, p95) under load.
  - Measure PySpark pipeline throughput and execution time across 3 repetitions with median and range.
  - Benchmark against an in-memory Python baseline on identical data.
- [x] Generate real machine-readable artifacts:
  - `artifacts/metrics.json`
  - `artifacts/test-results.xml`
  - `artifacts/benchmark-results.json`
  - `artifacts/benchmark-report.md`
  - `artifacts/data-quality-report.md`
  - `artifacts/resume-evidence.md`
- *Acceptance Criteria*: All metrics populated with real measured data; zero fabricated numbers. [PASSED]

### Milestone 7: Documentation & Verifiable Résumé Bullets
- [x] Author all required documentation in `docs/`:
  - `business-requirements.md`
  - `architecture.md`
  - `data-dictionary.md`
  - `segment-rules.md`
  - `testing-and-benchmarks.md`
  - `troubleshooting.md`
  - `demo-script.md`
  - `interview-preparation.md`
- [x] Author `README.md`, `Dockerfile`, and `docker-compose.yml`.
- [x] Author `docs/resume-bullets.md` containing 3 verifiable XYZ bullets tied directly to `artifacts/resume-evidence.md`.
- *Acceptance Criteria*: Every claim in résumé bullets maps to verifiable artifacts produced by automated runs. [PASSED]
