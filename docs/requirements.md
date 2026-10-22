# Fan360 Requirements & Acceptance Criteria
## Technical Specification: Data Pipeline & AI Audience Requirement Interpreter

> **Context & Educational Scope**: This document specifies the software requirements for **Fan360**, an educational customer data and audience segmentation platform designed for an Adobe Customer Services (ACS) Technical Consultant application (Domain 3: Python + PySpark + SQL — Data & AI Engineering).
> 
> All requirements represent **implemented behavior observed in source code** or explicitly noted **known limitations / proposed extensions**. No claims of real enterprise client delivery or external regulatory certification are made.

---

## 1. User Persona & Problem Statement

### 1.1 Intended User
- **Technical Consultant / Marketing Operations Specialist**: A technical user responsible for ingesting multi-channel fan data, auditing data hygiene, creating target audiences for personalized activation, and translating conversational marketing campaign criteria into precise query filters.

### 1.2 Core Problem
1. **Siloed & Corrupt Customer Touchpoints**: Fan interactions across merchandise orders, website sessions, email campaigns, and consent forms arrive with formatting defects, missing foreign keys, negative order amounts, and duplicate events.
2. **Consent Governance Violations**: Traditional marketing systems often conflate behavioral qualifications (e.g. repeat buyers) with outbound messaging eligibility, risking marketing activation to non-consenting customers.
3. **Ambiguity & Fragility in Campaign Ideation**: Marketers communicate in conversational language (e.g., *"Find our high-spending UK fans"* or *"Target super fans"*). Manual SQL translation is slow, prone to SQL injection, and often makes unverified assumptions about undefined business terms.

---

## 2. System Requirements Matrix

### 2.1 Core Ingestion, Transformation & Governance Requirements

| Requirement ID | Requirement Name | Description | Status |
| :--- | :--- | :--- | :--- |
| **REQ-001** | Unified Customer Profile | Consolidate fan demographics (`country`, `language`, `preferred_driver`), total completed spend in USD, order counts, and last activity timestamp into a unified table (`fan_profiles`). | **Implemented** |
| **REQ-002** | Hierarchical Data Validation & Quarantine | Validate raw CSV inputs against structural, referential, temporal, and value-domain checks. Quarantine invalid records with explicit reason codes (`MISSING_REQUIRED_FIELD`, `UNKNOWN_FAN_REFERENCE`, `INVALID_TIMESTAMP`, `INVALID_ORDER_AMOUNT`, `INVALID_CONSENT_STATUS`) with zero double-counting, maintaining exact row reconciliation balance. | **Implemented** |
| **REQ-003** | Latest-Effective Consent Resolution | Resolve marketing consent using the latest event timestamp per fan with deterministic tie-breaking. Non-consenting statuses (`OPT_OUT`, `NONE`, or missing) must never be assumed as permission. | **Implemented** |
| **REQ-004** | Idempotent Storage & Pipeline Auditability | Guarantee identical record counts and deterministic state across repeated pipeline executions on unchanged raw inputs using primary keys, `ON CONFLICT DO UPDATE` upserts, and SHA256 run hashing. | **Implemented** |
| **REQ-005** | Distributed PySpark Aggregations | Perform fan lifetime spend aggregation, order counts, and activity windowing using PySpark DataFrame transformations and window functions. | **Implemented** |
| **REQ-006** | Documented Cohort Segmentation | Automatically evaluate fans against 5 deterministic business segments: *Engaged Non-Buyers*, *Repeat Buyers*, *High-Spending Buyers*, *Inactive Fans*, and *Abandoned Cart*. | **Implemented** |
| **REQ-007** | Programmatic REST API & Dashboard | Expose profile lookup, segment members, audit logs, and data quality metrics via FastAPI (port 8000) and an interactive Streamlit UI (port 8501). | **Implemented** |

---

### 2.2 AI-Assisted Audience Requirement Interpreter Requirements

| Requirement ID | Requirement Name | Description | Status |
| :--- | :--- | :--- | :--- |
| **REQ-008** | Natural-Language Requirement Translation | Accept plain-English audience requirements and translate them into a structured JSON proposal matching the `ProposedSegment` schema. | **Implemented** |
| **REQ-009** | Strict Allowlisted Attribute Validation | Filter fields must be strictly allowlisted (`valid_completed_order_count`, `total_valid_spend`, `country`, `language`, `preferred_driver`, `days_since_last_activity`). Any unlisted field (e.g. `credit_score`, `age`) must be rejected. | **Implemented** |
| **REQ-010** | Conjunctive-Only Filter Logic (AND) | Support conjunctive (AND) expressions with up to 5 filters. Disjunctive (`OR`) expressions and nested logic must be rejected or routed to clarification. | **Implemented** |
| **REQ-011** | Ambiguity & Undefined Threshold Detection | When input contains undefined terms (e.g. "super fan", "VIP", "loyal" without threshold), the system must set `clarification_required=True` and generate a `clarification_question` asking for numeric parameters. | **Implemented** |
| **REQ-012** | Input Validation & Length Boundaries | Reject empty requirements or requests exceeding 1,000 characters. Validate numeric filter boundaries ($0 \le \text{spend} \le \$10,000,000$, $0 \le \text{orders} \le 100,000$, finite numbers only). | **Implemented** |
| **REQ-013** | Zero Customer Data Transmission (Privacy Boundary) | Outbound LLM requests must contain ONLY the user's requirement prompt and the allowlisted schema metadata. Zero customer PII, customer profile rows, database connection strings, or query results may be transmitted to external providers. | **Implemented** |
| **REQ-014** | Two-Stage Human Review Workflow | Propose filters in a reviewable, editable interface before any database evaluation or export occurs. The user must explicitly inspect or modify proposed thresholds before initiating audience preview. | **Implemented** |
| **REQ-015** | Preview-Time Payload Revalidation | When the client submits a proposed segment for preview, the backend must re-validate the entire payload against `ProposedSegment` before query generation, preventing tampered or bypass payloads. | **Implemented** |
| **REQ-016** | Inert SQL Parameterization | The query builder must generate strictly parameterized SQL queries using `%s` placeholders. Dynamic string concatenation of user values is forbidden, ensuring complete immunity to SQL injection. | **Implemented** |
| **REQ-017** | Mandatory Marketing Consent Segregation | The evaluation engine must strictly segregate total behavioral matches (`total_matched`) from activation-eligible members (`consent_eligible`). Only fans with active `marketing_consent_status = 'OPT_IN'` are eligible for campaign activation. Consent cannot be bypassed or overridden by prompt instructions. | **Implemented** |
| **REQ-018** | Explicit Mode Enforcement (Zero Silent Fallback) | The provider adapter must operate in explicit modes (`LLM_MODE=mock` or `LLM_MODE=live`). When `live` mode is requested without valid credentials or encounters an error, the system must fail fast with descriptive HTTP 503 / 502 status codes—it must NEVER silently fall back to mock mode. | **Implemented** |
| **REQ-019** | Bounded Transient Retries & Error Taxonomy | The live provider must classify errors into a clear domain taxonomy (`ConfigurationError`, `AuthenticationError`, `RateLimitError`, `ProviderTimeoutError`, `ProviderRefusalError`, `ProviderPayloadError`) and implement at most 1 bounded retry for transient 500/503 HTTP codes. | **Implemented** |
| **REQ-020** | Automated Traceability & Evaluation Suite | Maintain a version-controlled frozen evaluation dataset (10 scenarios) and automated verification script (`scripts/eval_ai_audience.py`) generating reproducible markdown benchmark reports (`artifacts/live-eval-report.md`). | **Implemented** |

---

## 3. Supported Attributes, Operators, and Business Rules

### 3.1 Allowlisted Schema Attributes

| Field Name | Type | Valid Operators | Value Constraints | Business Meaning |
| :--- | :--- | :--- | :--- | :--- |
| `valid_completed_order_count` | `int` | `>=`, `>`, `==`, `<=`, `<`, `!=` | $0 \le v \le 100,000$ | Total verified completed merchandise purchases. Repeat purchasers defined as $\ge 2$. |
| `total_valid_spend` | `float` | `>=`, `>`, `<=`, `<` | $\$0.00 \le v \le \$10,000,000.00$ | Total USD monetary spend across completed orders. High spenders defined as $\ge \$250.00$. |
| `country` | `str` | `==`, `!=`, `in` | Length 3 (ISO-3 alpha-3, e.g. USA, GBR, FRA, BRA, DEU) | Fan residential country. |
| `language` | `str` | `==`, `!=`, `in` | Length 2 (ISO-2, e.g. en, fr, es, pt, de) | Preferred communication language. |
| `preferred_driver` | `str` | `==`, `!=` | Max 64 chars (e.g. Lucas Rossi, Elena Vance) | Favorite motorsport racing driver. |
| `days_since_last_activity` | `int` | `>`, `>=`, `<=`, `<` | $0 \le v \le 36,500$ | Days since last website visit, order, or email interaction. Inactive fans defined as $> 180$. |

---

## 4. Known Limitations & Future Enhancements

### 4.1 Current Limitations
1. **Conjunctive Logic Only**: The current query builder supports only logical `AND` combinations. Disjunctive (`OR`) expressions across heterogeneous attributes require separate audience queries or explicit `in` lists on categorical fields.
2. **Batch Processing Boundary**: Audience membership and profile metrics are calculated against batch snapshots (e.g., daily runs). Streaming event evaluation is out of scope for this architecture.
3. **Local Database Scope**: The implementation is designed for single-node PostgreSQL execution; distributed analytical query engines (e.g. Trino, Snowflake, or Adobe AEP Query Service) are simulated via local relational SQL.

### 4.2 Proposed Future Enhancements (Non-Implemented)
- **Nested Expression Trees**: Extending `ProposedSegment` to support recursive AST structures for combined `AND` / `OR` Boolean grouping.
- **Automated Lookalike Modeling**: Using vector embeddings of profile attributes to propose seed audience expansions.
