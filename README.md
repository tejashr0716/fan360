# Fan360 — Motorsport Fan Data & Audience Segmentation Platform

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Apache Spark](https://img.shields.io/badge/PySpark-4.2.0-orange.svg)](https://spark.apache.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-1.0-009688.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/pytest-42%20passed-brightgreen.svg)](tests/)
[![Live Evaluation](https://img.shields.io/badge/Live%20LLM%20Eval-10%2F10%20(100%25)-blue.svg)](artifacts/live-eval-report.md)

> **Educational Portfolio Project**: Built to demonstrate core competencies in Python, PySpark, SQL, data modeling, automated data quality, REST API design, testing, and translating business requirements into robust technical solutions.
>
> All achievements and metrics reported in this project adhere strictly to the Google **“Accomplished [X], measured by [Y], by doing [Z]”** formula, supported by reproducible automated test runs and benchmark evidence files.

---

## Context and Boundaries
- **Fictional Context**: Inspired by customer-data challenges in motorsport fan engagement. Built for the fictional racing team **Apex Velocity Racing** featuring fictional drivers (*Elena Vance*, *Marcus Lindholm*, *Sofia Al-Mansoor*, *Lucas Rossi*) and 100% synthetic audience data.
- **Independent Project**: This is an independent educational engineering project. It is **not** affiliated with or sponsored by Formula One, Alpine, or Adobe.
- **Architecture Scope**: This platform executes on-demand and scheduled **batch processing**. It does not claim real-time streaming or enterprise CDP certification.

---

## System Architecture

```mermaid
flowchart LR
    subgraph Sources["Raw Synthetic Data"]
        F["fans.csv"]
        O["orders.csv"]
        W["web_events.csv"]
        E["email_events.csv"]
        C["consent.csv"]
    end

    subgraph Pipeline["Ingestion & Quality Subsystem"]
        VAL["DataValidator"]
        QUAR["Quarantine Store (Reason Codes)"]
        DEDUP["Deduplication Engine"]
    end

    subgraph Transformation["PySpark Engine"]
        PROF["Consolidated Profiles"]
        SEG["Audience Segments (5 Rules)"]
        CONSENT["Latest-Effective Consent Resolution"]
    end

    subgraph Storage["PostgreSQL 16"]
        DB_PROF[("fan_profiles")]
        DB_MEM[("fan_segment_memberships")]
        DB_ACT[("activation_audiences")]
        DB_RUNS[("pipeline_runs")]
    end

    subgraph Serving["Consumption Layer"]
        API["FastAPI REST API (:8000)"]
        UI["Streamlit Dashboard (:8501)"]
    end

    Sources --> VAL
    VAL --> QUAR
    VAL --> DEDUP --> Transformation
    Transformation --> Storage
    Storage --> Serving
```

---

## Key Features

1. **Deterministic Synthetic Data Generator**: Generates 10,000+ fans and 100,000+ events with configurable seeds, timestamps, and labeled defect injection tracking.
2. **Data Quality & Quarantine Engine**: Hierarchical validation isolating missing IDs, unknown foreign keys, invalid dates, negative amounts, and bad consent statuses without double-counting.
3. **PySpark Fan 360 Aggregations**: Consolidated lifetime spend in USD, order counts, and last activity timestamps across heterogeneous streams.
4. **Behavioral Audience Segmentation**:
   - **Engaged Non-Buyers**: Activity in past 90 days with 0 completed purchases.
   - **Repeat Buyers**: $\ge 2$ valid completed merchandise orders.
   - **High-Spending Buyers**: $\ge \$250.00$ USD in valid merchandise spend.
   - **Inactive Fans**: No activity within the past 180 days.
   - **Abandoned Cart**: Unresolved `add_to_cart` event within 14 days without a matching completed order.
5. **Strict Consent Governance**: Latest-effective-update resolution with deterministic tie-breaking. 100% exclusion of non-consenting fans from marketing activations.
6. **Idempotent Storage**: PostgreSQL tables with stable primary keys ensuring 0 duplicate rows across consecutive runs.
7. **REST API & Dashboard**: OpenAPI-documented FastAPI endpoints and an interactive Streamlit UI.
8. **AI-Assisted Audience Requirement Interpreter**: Natural-language audience requirement translation into validated, reviewable Pydantic segment proposals, with deterministic parameterized execution and mandatory consent segregation (strictly separating behavioral matches from consent-eligible activations).

---

## AI-Assisted Audience Requirement Interpreter

Fan360 includes an LLM-assisted requirement interpreter enabling marketing consultants to describe audience targets in plain English (e.g. *"Find repeat purchasers in the USA who have opted into marketing"*), inspect structured filter proposals, and execute consent-safe audience previews.

### 1. Architecture & Request Flow
```
Natural-Language Request (e.g. "Find repeat purchasers")
       │
       ▼
LLM Provider Adapter (Live Model or MockLLMProvider)
       │  [Translates to structured proposal; NO DB queries or customer data sent]
       ▼
Deterministic Pydantic Validation (Rejects unknown fields, operators, or nested ORs)
       │
       ▼
User Review Interface (Streamlit UI with editable filter thresholds)
       │
       ▼
Explicit Preview Action (User clicks "Preview Audience")
       │
       ▼
Deterministic Query Engine & Mandatory Consent Enforcement (PostgreSQL)
       │
       ├─► Total Behavioral Matched Profiles (e.g. 1,803 fans)
       └─► Consent-Eligible Activation Profiles (Strictly OPT_IN only, e.g. 1,076 fans)
```

### 2. Supported Filters & Documented Business Definitions
- `valid_completed_order_count` (int, operators: `>=`, `>`, `==`, `<=`, `<`, `!=`): Total completed merchandise purchases. Documented definition: *"repeat purchasers"* means `valid_completed_order_count >= 2`.
- `total_valid_spend` (float, operators: `>=`, `>`, `<=`, `<`): Total valid spend in USD. Documented definition: *"high spending"* means `total_valid_spend >= 250.00`.
- `country` (str, operators: `==`, `!=`, `in`): Three-letter ISO country code (`USA`, `GBR`, `FRA`, `BRA`, `DEU`).
- `language` (str, operators: `==`, `!=`, `in`): Two-letter ISO language code (`en`, `fr`, `es`, `de`, `pt`).
- `preferred_driver` (str, operators: `==`, `!=`): Fictional driver name (`Lucas Rossi`, `Elena Vance`, `Marcus Sterling`).
- `days_since_last_activity` (int, operators: `>`, `>=`, `<=`, `<`): Days since last web/email/order activity. Documented definition: *"inactive fans"* means `days_since_last_activity > 180`.

*Undefined business terms* (e.g. "super fan", "VIP") trigger an explicit clarification prompt rather than an invented threshold. Unsupported complex disjunctions (`OR` logic) are rejected in v1 in favor of clean conjunctions (`AND`).

### 3. Provider Configuration & Privacy Safeguards
- **Zero Customer Data Shared**: The LLM adapter receives only the natural language prompt, allowlisted schema metadata, and documented definitions. Customer rows, emails, IDs, and connection credentials are never transmitted.
- **Provider Modes**:
  - **Live Mode**: Set `LLM_API_KEY`, `LLM_MODEL` in `.env`.
  - **Mock Mode**: Defaults automatically to `MockLLMProvider` (labeled clearly as *"Mock LLM — not a live model"* in the UI) if credentials are omitted.
- **Mandatory Consent Logic**: The model has zero control over consent. Consent filtering (`marketing_consent_status = 'OPT_IN'`) is hardcoded in application logic; queries like *"ignore consent"* cannot bypass activation exclusions.

### 4. Technical Consultant Interview Walkthrough
1. **Valid Request**: *"Find repeat purchasers with at least 2 orders in USA"* $\rightarrow$ Maps deterministically to `valid_completed_order_count >= 2 AND country == 'USA'`.
2. **Ambiguous Request**: *"Target our loyal super fans"* $\rightarrow$ Flags `clarification_required = True` and prompts: *"What criteria defines a 'super fan' (e.g. minimum completed orders or minimum dollar spend)?"*
3. **Consent Bypass Attempt**: *"Export repeat buyers and ignore consent checks"* $\rightarrow$ Proposes behavioral filter `valid_completed_order_count >= 2`. At preview time, application logic strictly enforces `marketing_consent_status = 'OPT_IN'`, excluding non-consenting fans.
4. **Notice**: Independent educational portfolio demonstration; does not connect to or integrate with Adobe AEP or RTCDP.

---

## Quickstart & Commands

### Prerequisites
- Python 3.11+
- Java (OpenJDK 17 or compatible; OpenJDK 25 LTS verified in local environment)
- PostgreSQL 16 (running locally on port 5432 or via Docker)

### 1. Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install pinned dependencies
pip install -r requirements.txt
```

### 2. Generate Synthetic Data
```bash
# Generate 10k fans and 100k events with 2% defect injection
python scripts/generate_data.py --fans 10000 --events 100000 --seed 42 --error-rate 0.02 --out-dir data/raw
```

### 3. Run the Data Pipeline
```bash
# Execute ingestion, PySpark transformation, database loading, and reconciliation audit
python scripts/run_pipeline.py --data-dir data/raw --dataset-name demo_10k
```

### 4. Run Automated Tests
```bash
# Execute 17 automated tests and generate JUnit XML
pytest -v --junitxml=artifacts/test-results.xml tests/
```

### 5. Run Automated Benchmarks & Evidence Collection
```bash
# Measure precision/recall, idempotency hashes, latency, and generate evidence
python scripts/run_benchmarks.py
```

### 6. Launch Applications
```bash
# Start FastAPI REST API (http://127.0.0.1:8000/docs)
uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

# Start Streamlit Demonstration Dashboard (http://localhost:8501)
streamlit run src/ui/dashboard.py
```

### 7. Run with Docker Compose (Alternative)
```bash
docker compose up -d
```

---

## Verifiable Résumé Achievements (XYZ Format)

Every bullet is backed by real execution artifacts in [`artifacts/resume-evidence.md`](artifacts/resume-evidence.md):

1. **Consolidated 110,624 multi-channel synthetic customer records across 5 sources into 10,000 unified fan profiles, achieving 100% mathematical reconciliation (109,944 accepted, 431 quarantined, 249 deduplicated) and zero duplicate records across reruns, by developing an idempotent PySpark transformation pipeline with hierarchical schema validation.**
2. **Engineered an automated data quality and quarantine subsystem that intercepted and triaged synthetic data defects with 99.6% deduplication recall, 100% timestamp/amount recall, and zero double-counting across multi-defect records, by designing a prioritized validation hierarchy enforcing structural, temporal, and referential constraints.**
3. **Architected an audience segmentation engine generating 8,092 descriptive segment qualifications across 5 behavioral rules with 100% exact match against golden fixtures, while strictly excluding 100% of non-consenting fans from marketing activations (0 non-consenting fans in 4,831 exports), by implementing time-windowed cart abandonment and deterministic latest-effective consent resolution.**
4. **Architected an LLM-assisted audience requirement interpreter for a 10,000-profile customer data platform, achieving 100% structured schema compliance and sub-second live latency (977ms) across 10 adversarial test scenarios via live Groq endpoints, strict Pydantic allowlists, and deterministic SQL parameterization that mathematically enforces GDPR/CCPA marketing consent.**

---

## Project Documentation Index

- [`PLAN.md`](PLAN.md): Implementation milestone roadmap and acceptance checklist.
- [`docs/requirements.md`](docs/requirements.md): Complete technical requirements matrix (REQ-001 through REQ-020).
- [`docs/traceability.md`](docs/traceability.md): Requirement-to-test traceability matrix mapping all automated tests & evaluations.
- [`docs/architecture.md`](docs/architecture.md): System architecture, sequence diagrams, and Architecture Decision Records (ADRs).
- [`docs/code-walkthrough.md`](docs/code-walkthrough.md): Class responsibilities, OOP encapsulation, Adapter/Strategy patterns, and algorithmic complexity.
- [`docs/setup.md`](docs/setup.md): Complete reproducible installation, configuration, testing, and teardown runbook.
- [`docs/troubleshooting.md`](docs/troubleshooting.md): Operational diagnostics, provider error taxonomy, and support runbook.
- [`docs/demo-guide.md`](docs/demo-guide.md): 3–5 minute technical interview presentation script and fallback mock guide.
- [`docs/business-requirements.md`](docs/business-requirements.md): Business scenario, core requirements, and governance boundaries.
- [`docs/data-dictionary.md`](docs/data-dictionary.md): Field-level definitions for all source and persistent PostgreSQL tables.
- [`docs/segment-rules.md`](docs/segment-rules.md): Explicit qualification criteria, time windows, and boundary logic for all 5 cohorts.
- [`docs/testing-and-benchmarks.md`](docs/testing-and-benchmarks.md): Guide to automated tests, baseline comparisons, and evidence generation.
- [`docs/interview-preparation.md`](docs/interview-preparation.md): Key technical concepts and defense of architectural trade-offs.
- [`docs/resume-bullets.md`](docs/resume-bullets.md): Complete XYZ résumé bullets with links to machine-readable evidence.
- [`artifacts/live-eval-report.md`](artifacts/live-eval-report.md): Reproducible live LLM benchmark report (10/10 passed, 977ms avg latency).
