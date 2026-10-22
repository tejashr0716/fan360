# Fan360 Data Quality & Defect Detection Report

**Generated**: 2026-10-22T17:55:48Z  
**Dataset**: Synthetic `demo_10k` (Seed `42`)  
**Defect Rate**: 2.0%

## 1. Input Reconciliation Audit
Reconciliation Formula: `Raw Ingestion = Accepted Rows + Quarantined Rows + Duplicates Removed`

| Table Name | Raw Ingested | Accepted Rows | Quarantined Rows | Duplicates Removed | Balanced Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `fans` | 10,000 | 10,000 | 0 | 0 | **BALANCED** |
| `orders` | 10,000 | 9,920 | 80 | 0 | **BALANCED** |
| `web_events` | 50,250 | 49,801 | 200 | 249 | **BALANCED** |
| `email_events` | 30,000 | 29,880 | 120 | 0 | **BALANCED** |
| `consent` | 10,374 | 10,343 | 31 | 0 | **BALANCED** |
| **TOTAL** | **110,624** | **109,944** | **431** | **249** | **100% BALANCED** |

## 2. Injected Defect Detection Precision & Recall
Measured against ground-truth labels injected by `src/generator/synthetic_data.py`:

| Defect Category | Ground Truth Injected | Detected Count | True Positives | False Positives | False Negatives | Precision | Recall |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `DUPLICATE_ID` | 250 | 249 | 249 | 0 | 1 | **100.0%** | **99.6%** |
| `MISSING_REQUIRED_FIELD` | 40 | 40 | 18 | 22 | 22 | **45.0%** | **45.0%** |
| `INVALID_TIMESTAMP` | 120 | 120 | 120 | 0 | 0 | **100.0%** | **100.0%** |
| `UNKNOWN_FAN_REFERENCE` | 201 | 200 | 200 | 0 | 1 | **100.0%** | **99.5%** |
| `INVALID_ORDER_AMOUNT` | 40 | 40 | 40 | 0 | 0 | **100.0%** | **100.0%** |
| `INVALID_CONSENT_STATUS` | 31 | 31 | 31 | 0 | 0 | **100.0%** | **100.0%** |

**Overall Detection Recall**: `96.5%`  
**Overall Detection Precision**: `96.8%`

## 3. Quarantine Hierarchy & Non-Double-Counting Rules
Records with multiple potential defects are evaluated deterministically in the following priority:
1. `MISSING_REQUIRED_FIELD` (Structural prerequisite)
2. `UNKNOWN_FAN_REFERENCE` (Referential integrity)
3. `INVALID_TIMESTAMP` (Temporal boundary)
4. `INVALID_ORDER_AMOUNT` (Domain boundary)
5. `INVALID_CONSENT_STATUS` (Enum validity)

This strict priority guarantees each corrupted record receives exactly one primary quarantine reason code and prevents double-counting across audit reports.
