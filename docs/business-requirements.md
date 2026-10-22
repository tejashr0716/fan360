# Business Requirements Document (BRD)
## Fan360 — Motorsport Fan Data & Audience Segmentation Platform

**Context**: Independent educational portfolio project inspired by motorsport customer-data challenges.  
**Fictional Entity**: Apex Velocity Racing (fictional racing team, fictional drivers, synthetic audience data).  
**Target Profile**: Entry-Level Data & AI Engineer / Technical Consultant.

---

## 1. Problem Statement & Business Background
A fictional motorsport team generates fan data across disconnected digital touchpoints:
1. **Fan Accounts**: Registrations, demographics, country, language, preferred driver.
2. **Merchandise Store**: Order transactions, items purchased, monetary amounts, order statuses, and carts.
3. **Website Engagement**: Telemetry viewers, video replays, race hub page visits, and session carts.
4. **Email Campaigns**: Newsletters, race previews, telemetry recaps, opens, clicks.
5. **Marketing Consent**: Opt-in/opt-out status submitted across web forms, unsubscribe links, and settings.

### Business Challenges
- **Data Fragmentation**: Marketing teams lack a single consolidated profile to understand fan lifetime value, engagement frequency, and driver affinity.
- **Data Quality Risks**: Unvalidated upstream events, duplicate payloads, invalid timestamps, and orphan events threaten to corrupt segmentation and marketing analytics.
- **Privacy & Compliance**: Sending marketing campaigns to fans who have opted out or withdrawn consent violates internal governance and customer trust. Missing consent must never be assumed as permission.
- **Lack of Transparency**: Marketing specialists cannot inspect why a fan qualified for a segment or why a fan was excluded from campaign activation.

---

## 2. Core Business Requirements & Technical Solutions

| Requirement ID | Business Requirement | Technical Implementation |
| :--- | :--- | :--- |
| **BR-01** | **Unified Fan Profile**<br>Consolidate fan details, total valid spend in USD, completed order counts, and last activity time into a single profile. | `SparkFanPipeline.process()` aggregates orders and activity across streams, calculating verified metrics and upserting into `fan_profiles`. |
| **BR-02** | **Actionable Audience Segments**<br>Segment fans into 5 behavioral groups: Repeat Buyers, High Spenders, Engaged Non-Buyers, Inactive Fans, and Abandoned Carts. | Config-driven rules in `config/segment_rules.yaml` evaluated in PySpark using time windows relative to a deterministic `as_of` timestamp. |
| **BR-03** | **Explainable Qualification**<br>Provide clear, human-readable reasons explaining why a fan entered a segment. | Stored `reason` string generated per membership (e.g. `Placed 3 completed orders (threshold: >= 2)`). |
| **BR-04** | **Strict Consent Enforcement**<br>Marketing activations must strictly exclude fans without verified opt-in consent. | Separation of descriptive `fan_segment_memberships` (all qualifying fans) from `activation_audiences` (strictly `marketing_consent_status = 'OPT_IN'`). Latest-effective update rule with deterministic tie-breaker applied. |
| **BR-05** | **Data Integrity & Quarantine**<br>Corrupted or invalid upstream records must be isolated with clear error codes rather than corrupting aggregates. | `DataValidator` applies hierarchical checks, routing invalid rows to `quarantine_records` without double-counting and maintaining 100% input reconciliation. |
| **BR-06** | **Idempotent Operations**<br>Pipeline re-runs on identical data must produce unchanged logical counts and outputs. | Stable primary keys, `ON CONFLICT DO UPDATE` upserts, and canonical content hash verification. |
| **BR-07** | **Operational Access & Visibility**<br>Provide programmatic API access and an interactive dashboard for marketing and engineering teams. | FastAPI service with OpenAPI documentation and Streamlit demonstration dashboard. |

---

## 3. Scope Boundaries & Governance
- **Not Real-Time**: Batch processing platform evaluated against scheduled or on-demand runs with configurable reference timestamps.
- **Fictional Data**: 100% synthetic data generated with deterministic pseudorandom seeds. No real customer PII or proprietary team data is used.
- **No Production Claims**: Designed as a clean local portfolio demonstration; does not claim regulatory GDPR/CCPA certification or enterprise cloud scale.
