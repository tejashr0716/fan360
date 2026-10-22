# Fan360 Implementation Plan

## Overview
Fan360 is an educational motorsport fan data and audience segmentation platform. This plan details the phased architecture, implementation milestones, and automated verification steps required to produce verified, reproducible résumé achievements in the XYZ format: “Accomplished [X], measured by [Y], by doing [Z].”

## Architecture & Technology Stack
- **Language**: Python 3.14 (pinned runtime in local `.venv`)
- **Transformations**: PySpark 4.2.0 (local engine running on OpenJDK 25)
- **Database**: PostgreSQL 16 (running locally on port 5432, with automated schema creation)
- **API**: FastAPI + Uvicorn + Pydantic v2
- **UI**: Streamlit
- **Testing**: pytest, pytest-cov
- **Benchmarking & Quality**: Custom deterministic audit scripts generating machine-readable evidence (`artifacts/`)

## Milestone Roadmap

### Milestone 1: Environment & Project Foundation (Current)
- [x] Verify local runtime: Python, Java, PostgreSQL, Git.
- [x] Pin dependencies in `requirements.txt` and install in `.venv`.
- [x] Create project layout, directories, and base configuration (`config/config.yaml`, `config/segment_rules.yaml`).
- [x] Write `PLAN.md`.
- *Acceptance Criteria*: Virtual environment active, PySpark and PostgreSQL connections verified.

### Milestone 2: Synthetic Data Generator & Deterministic Fixtures
- [ ] Implement `src/generator/synthetic_data.py`:
  - Fictional motorsport context (Apex Velocity Racing, fictional drivers).
  - Generator manifest tracking seed, intended counts, and injected defect categories.
  - Injected defects: duplicate IDs, missing required fields, invalid timestamps, orphan fans, negative amounts, conflicting consent updates.
- [ ] Create small hand-authored golden test fixtures (`tests/fixtures/`) with 100% human-verified ground truth.
- [ ] Implement CLI generator command (`scripts/generate_data.py`) with configurable volume, seed, error rates, and fixed "as of" timestamp.
- *Acceptance Criteria*: Generator creates reconcilable raw data and manifest; fixtures match strict schema.

### Milestone 3: Data Quality, Quarantine & PySpark Pipeline
- [ ] Implement data quality engine (`src/pipeline/validation.py`):
  - Field-level & schema validation with unambiguous reason codes.
  - Non-double-counting quarantine logic.
  - Deterministic deduplication.
- [ ] Implement PySpark ETL and enrichment pipeline (`src/pipeline/spark_pipeline.py`):
  - Ingest raw sources.
  - Build consolidated fan profiles (last activity, valid completed order count, total valid spend in USD, latest resolved marketing consent).
  - Calculate audience segments based on `config/segment_rules.yaml`.
  - Documented cart-abandonment matching session/cart and purchase resolution.
  - Separation of descriptive segment qualification vs. consent-based activation eligibility.
  - Per-membership explanation reason payloads.
- [ ] Implement database loading & idempotent storage (`src/pipeline/db_loader.py`):
  - PostgreSQL tables for profiles, events, consents, segments, memberships, quarantines, and run audit.
  - Idempotent upsert logic with stable primary keys.
- *Acceptance Criteria*: End-to-end pipeline executes on fixtures and full dataset; audit report reconciles raw, accepted, deduplicated, and quarantined counts.

### Milestone 4: FastAPI REST API & Streamlit Dashboard
- [ ] Implement FastAPI application (`src/api/app.py`):
  - `GET /health`
  - `GET /fans/{fan_id}`
  - `GET /segments`
  - `GET /segments/{segment_name}/members` (with pagination, activation-only filter, and reasons)
  - `GET /runs/{run_id}/quality`
- [ ] Implement Streamlit dashboard (`src/ui/dashboard.py`):
  - Run & reconciliation summary.
  - Data quality & quarantine explorer.
  - Fan profile search & activity timeline.
  - Segment membership reasons & consent-filtered activation audience preview.
- *Acceptance Criteria*: All API endpoints return valid JSON matching schemas; Streamlit UI renders without exceptions.

### Milestone 5: Automated Testing Suite
- [ ] Implement comprehensive test suite (`tests/`):
  1. Small known fixture transformation.
  2. Exact hand-authored segment memberships comparison.
  3. Threshold and time-window boundary conditions.
  4. Deduplication correctness.
  5. Quarantine reason code assignment.
  6. Consent eligibility filtering.
  7. Consent withdrawal reflection.
  8. Idempotent rerun verification (row counts & SHA256 canonical output hashes).
  9. Fan profile spend & order count aggregations.
  10. API pagination, validation, and error handling.
  11. Database integration tests.
  12. Complete end-to-end pipeline run test.
- *Acceptance Criteria*: `pytest` runs and passes 100% of non-skipped tests, outputs `artifacts/test-results.xml`.

### Milestone 6: Measurement, Benchmarking & Evidence Generation
- [ ] Implement benchmarking and quality audit runner (`scripts/run_benchmarks.py`):
  - Measure detection precision and recall against labeled synthetic defects.
  - Verify idempotency across consecutive runs.
  - Measure API response latency (p50, p95) under load.
  - Measure PySpark pipeline throughput and execution time across multiple runs.
- [ ] Generate real machine-readable artifacts:
  - `artifacts/metrics.json`
  - `artifacts/benchmark-results.json`
  - `artifacts/benchmark-report.md`
  - `artifacts/data-quality-report.md`
  - `artifacts/resume-evidence.md`
- *Acceptance Criteria*: All metrics populated with real measured data; zero fabricated numbers.

### Milestone 7: Documentation & Verifiable Résumé Bullets
- [ ] Author all required documentation in `docs/`:
  - `business-requirements.md`
  - `architecture.md`
  - `data-dictionary.md`
  - `segment-rules.md`
  - `testing-and-benchmarks.md`
  - `troubleshooting.md`
  - `demo-script.md`
  - `interview-preparation.md`
- [ ] Author `README.md` and `docker-compose.yml`.
- [ ] Author `docs/resume-bullets.md` containing 3 verifiable XYZ bullets tied directly to `artifacts/resume-evidence.md`.
- *Acceptance Criteria*: Every claim in résumé bullets maps to verifiable artifacts produced by automated runs.
