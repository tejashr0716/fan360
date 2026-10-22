# Troubleshooting & Operations Guide
## Fan360 Common Issues and Diagnostic Runbook

---

## 1. Environment & Runtime Issues

### Issue 1: Java Version or JVM Module Warnings
- **Symptoms**: Warnings such as `Using incubator modules: jdk.incubator.vector` or `package sun.security.action not in java.base` when starting PySpark.
- **Root Cause**: Modern OpenJDK (versions 21 through 25) enforce stricter module encapsulation.
- **Resolution**: These are standard JDK warnings that do not prevent execution. Fan360 configures Spark local sessions to suppress noisy log4j levels (`log_level: WARN`). If running in production or Docker, use OpenJDK 17 LTS.

### Issue 2: PostgreSQL Connection Refused
- **Symptoms**: `psycopg2.OperationalError: could not connect to server: Connection refused`.
- **Diagnosis**:
  ```bash
  psql -U tejashr -d fan360 -c "SELECT 1;"
  ```
- **Resolution**:
  - Check if local PostgreSQL is running:
    ```bash
    brew services list
    brew services start postgresql@16
    ```
  - Verify database credentials in `config/config.yaml` or set environment variables:
    ```bash
    export FAN360_DB_HOST=localhost
    export FAN360_DB_PORT=5432
    export FAN360_DB_NAME=fan360
    export FAN360_DB_USER=$(whoami)
    ```

---

## 2. Sample Data Quality Issue & Step-by-Step Diagnosis

### Scenario: Marketing team reports that a known high-value fan (`FAN_000045`) is missing from the "High-Spending Buyers" activation export.

### Diagnostic Steps:
1. **Check if the fan exists in consolidated profiles**:
   ```bash
   curl -s http://127.0.0.1:8000/fans/FAN_000045 | jq .
   ```
   *Observation*: `total_valid_spend` is \$140.00, below the \$250.00 threshold, but marketing claims the fan spent \$340.00.

2. **Query quarantined records for this fan's orders**:
   ```sql
   SELECT source_table, record_id, reason_code, raw_payload
   FROM quarantine_records
   WHERE raw_payload->>'fan_id' = 'FAN_000045';
   ```
   *Findings*:
   - Row 1: `order_id = ORD_000120`, `reason_code = 'INVALID_ORDER_AMOUNT'`. Payload shows `order_amount = -200.00`.
   - The merchandise store ingested a refund/chargeback as a negative raw amount rather than a return event.
   - The validation engine correctly quarantined the record before it could distort spend calculations.

3. **Check consent status**:
   *Observation*: `marketing_consent_status` is `OPT_OUT`. Even if total valid spend exceeded \$250, the fan is legally excluded from campaign activation under internal data governance policy.

4. **Resolution**:
   - Upstream order integration must categorize returns separately from gross spend.
   - Clarify to marketing that consent exclusion protects customer privacy and brand reputation.

---

## 3. Data Reconciliation Discrepancy Diagnosis
If the pipeline reports `reconciliation_status: DISCREPANCY`:
1. Check table-by-table counts in `pipeline_runs.audit_details`:
   ```sql
   SELECT run_id, reconciliation_status, audit_details
   FROM pipeline_runs
   ORDER BY started_at DESC LIMIT 1;
   ```
2. Verify if any duplicate rows were counted as quarantined:
   - Deduplication must be tracked in `duplicates_removed` and excluded from `quarantine_records` to prevent double-counting.
