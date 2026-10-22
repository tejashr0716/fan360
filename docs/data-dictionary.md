# Data Dictionary & Schema Reference
## Fan360 Motorsport Fan Data Platform

---

## 1. Source Tables (Input Schema)

### `fans.csv`
Fan account demographic master records.
- `fan_id` (VARCHAR, PK): Unique stable identifier (e.g. `FAN_000001`).
- `first_name` (VARCHAR): Fan given name.
- `last_name` (VARCHAR): Fan family name.
- `email` (VARCHAR): Contact email address.
- `country` (VARCHAR): ISO 3166-1 alpha-3 country code (e.g. `GBR`, `USA`, `ITA`).
- `language` (VARCHAR): Preferred language code (e.g. `en`, `it`, `fr`).
- `preferred_driver` (VARCHAR): Fictional driver name (`Elena Vance`, `Marcus Lindholm`, `Sofia Al-Mansoor`, `Lucas Rossi`).
- `created_at` (TIMESTAMPTZ): ISO 8601 UTC timestamp of account registration.

### `orders.csv`
Merchandise purchase transactions.
- `order_id` (VARCHAR, PK): Unique transaction identifier (e.g. `ORD_000001`).
- `fan_id` (VARCHAR, FK): Foreign key referencing `fans.fan_id`.
- `order_status` (VARCHAR): Transaction status (`COMPLETED`, `CANCELLED`, `REFUNDED`, `PENDING`).
- `order_amount` (NUMERIC): Order value in USD (must be > 0.00).
- `currency` (VARCHAR): Currency code (fixed to `USD`).
- `order_timestamp` (TIMESTAMPTZ): ISO 8601 UTC timestamp of purchase.
- `items_count` (INT): Number of distinct merchandise units purchased.
- `cart_id` (VARCHAR, optional): Associated shopping cart identifier.

### `web_events.csv`
Website and digital media engagement interactions.
- `event_id` (VARCHAR, PK): Unique event identifier (e.g. `WEB_000001`).
- `fan_id` (VARCHAR, FK): Foreign key referencing `fans.fan_id`.
- `session_id` (VARCHAR): Digital session identifier.
- `event_type` (VARCHAR): Interaction type (`page_view`, `add_to_cart`, `video_view`, `telemetry_view`).
- `event_timestamp` (TIMESTAMPTZ): ISO 8601 UTC timestamp of event.
- `page_url` (VARCHAR): Web route or resource accessed.
- `cart_id` (VARCHAR, optional): Cart identifier present on `add_to_cart` events.

### `email_events.csv`
Direct communication campaign interactions.
- `event_id` (VARCHAR, PK): Unique email interaction identifier (e.g. `EML_000001`).
- `fan_id` (VARCHAR, FK): Foreign key referencing `fans.fan_id`.
- `campaign_id` (VARCHAR): Marketing campaign code (e.g. `CMP_MONZA_PREVIEW_2026`).
- `action` (VARCHAR): Action taken (`sent`, `opened`, `clicked`).
- `event_timestamp` (TIMESTAMPTZ): ISO 8601 UTC timestamp of email interaction.

### `consent.csv`
Marketing communication permissions log.
- `consent_id` (VARCHAR, PK): Unique consent event identifier (e.g. `CNS_000001`).
- `fan_id` (VARCHAR, FK): Foreign key referencing `fans.fan_id`.
- `consent_type` (VARCHAR): Category of consent (e.g. `marketing_email`).
- `status` (VARCHAR): Opt-in status (`OPT_IN` or `OPT_OUT`).
- `update_timestamp` (TIMESTAMPTZ): ISO 8601 UTC timestamp of consent submission.
- `channel` (VARCHAR): Origin channel (`web_form`, `account_settings`, `unsubscribe_link`).

---

## 2. PostgreSQL Persistent Database Tables

### `fan_profiles`
Consolidated single view of the fan.
- `fan_id` (VARCHAR(64), PK): Unique fan identifier.
- `first_name` (VARCHAR(128)): Given name.
- `last_name` (VARCHAR(128)): Family name.
- `email` (VARCHAR(256)): Verified email address.
- `country` (VARCHAR(32)): Country code.
- `language` (VARCHAR(16)): Language preference.
- `preferred_driver` (VARCHAR(128)): Driver affinity.
- `created_at` (TIMESTAMPTZ): Account creation time.
- `last_activity_time` (TIMESTAMPTZ): Latest timestamp across orders, web events, email events, or creation.
- `valid_completed_order_count` (INT): Total number of valid `COMPLETED` merchandise orders with amount > 0.
- `total_valid_spend` (NUMERIC(12, 2)): Total monetary spend in USD from valid completed orders.
- `marketing_consent_status` (VARCHAR(32)): Resolved consent status (`OPT_IN`, `OPT_OUT`, or `NONE`).
- `last_run_id` (VARCHAR(64)): Identifier of pipeline run that updated this row.
- `updated_at` (TIMESTAMPTZ): Modification timestamp.

### `segment_definitions`
Lookup table of available audience segments and business rules.
- `segment_code` (VARCHAR(64), PK): Canonical segment slug (e.g. `repeat_buyers`).
- `segment_name` (VARCHAR(128)): Human-readable title.
- `description` (TEXT): Business explanation.
- `rules_json` (JSONB): Structured configuration parameters.

### `fan_segment_memberships`
Descriptive qualification records for each fan and segment.
- `fan_id` (VARCHAR(64), FK): References `fan_profiles.fan_id`.
- `segment_code` (VARCHAR(64), FK): References `segment_definitions.segment_code`.
- `qualifies` (INT): 1 if the fan satisfies the rule criteria, 0 otherwise.
- `activation_eligible` (INT): 1 if `qualifies = 1` AND `marketing_consent_status = 'OPT_IN'`, 0 otherwise.
- `reason` (TEXT): Audit explanation detailing specific metrics that triggered qualification.
- `last_run_id` (VARCHAR(64)): Pipeline run identifier.
- `updated_at` (TIMESTAMPTZ): Modification timestamp.
- *Primary Key*: `(fan_id, segment_code)`

### `activation_audiences`
Marketing campaign activation export table. Strictly contains fans who qualified AND possess `OPT_IN` consent.
- `fan_id` (VARCHAR(64)): Fan identifier.
- `segment_code` (VARCHAR(64)): Audience segment code.
- `email` (VARCHAR(256)): Recipient email address.
- `first_name` (VARCHAR(128)): Given name.
- `last_name` (VARCHAR(128)): Family name.
- `consent_status` (VARCHAR(32)): Consent status (`OPT_IN`).
- `last_run_id` (VARCHAR(64)): Run identifier.
- `created_at` (TIMESTAMPTZ): Creation timestamp.
- *Primary Key*: `(fan_id, segment_code, last_run_id)`

### `quarantine_records`
Audit storage for records that failed quality or integrity checks.
- `id` (SERIAL, PK): Auto-incrementing identifier.
- `run_id` (VARCHAR(64)): Pipeline run during which the defect was isolated.
- `source_table` (VARCHAR(64)): Source file (`orders`, `web_events`, etc.).
- `record_id` (VARCHAR(64)): Corrupted record's primary identifier.
- `reason_code` (VARCHAR(64)): Diagnostic code (`MISSING_REQUIRED_FIELD`, `INVALID_TIMESTAMP`, etc.).
- `raw_payload` (JSONB): Full original record payload.
- `created_at` (TIMESTAMPTZ): Quarantine timestamp.

### `pipeline_runs`
Run-level audit and reconciliation tracking.
- `run_id` (VARCHAR(64), PK): Unique run execution identifier.
- `dataset_name` (VARCHAR(64)): Input dataset identifier.
- `as_of_timestamp` (TIMESTAMPTZ): Reference timestamp used for evaluation.
- `started_at` (TIMESTAMPTZ): Start timestamp.
- `completed_at` (TIMESTAMPTZ): Completion timestamp.
- `status` (VARCHAR(32)): `SUCCESS` or `FAILED`.
- `raw_records_count` (INT): Total rows ingested.
- `accepted_records_count` (INT): Rows passing validation.
- `quarantined_records_count` (INT): Rows quarantined.
- `duplicates_removed_count` (INT): Duplicate rows removed.
- `profiles_count` (INT): Fan profiles generated.
- `memberships_count` (INT): Total segment qualifications.
- `activation_count` (INT): Consent-eligible fans exported.
- `reconciliation_status` (VARCHAR(32)): `BALANCED` or `DISCREPANCY`.
- `audit_details` (JSONB): Execution metadata and execution duration.
