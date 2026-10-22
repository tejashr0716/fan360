"""
Tests for Validation and Quarantine Engine
Tests field checks, referential integrity, timestamp boundaries, and non-double-counting reconciliation.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.validation import DataValidator


def load_fixture_csv(file_path: Path) -> List[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def test_fixture_validation_and_reconciliation() -> None:
    fixtures_dir = Path("tests/fixtures")
    raw_data = {
        "fans": load_fixture_csv(fixtures_dir / "fans.csv"),
        "orders": load_fixture_csv(fixtures_dir / "orders.csv"),
        "web_events": load_fixture_csv(fixtures_dir / "web_events.csv"),
        "email_events": load_fixture_csv(fixtures_dir / "email_events.csv"),
        "consent": load_fixture_csv(fixtures_dir / "consent.csv"),
    }

    validator = DataValidator(as_of_timestamp="2026-10-01T00:00:00Z")
    accepted, quarantines, dups, quarantined_counts = validator.validate_and_quarantine(raw_data)

    # 1. Verify Reconciliation: Raw = Accepted + Quarantined + Duplicates Removed for each table
    for table_name in raw_data.keys():
        raw_count = len(raw_data[table_name])
        acc_count = len(accepted[table_name])
        quar_count = quarantined_counts[table_name]
        dup_count = dups[table_name]
        assert raw_count == acc_count + quar_count + dup_count, (
            f"Table {table_name} failed reconciliation: raw={raw_count}, accepted={acc_count}, "
            f"quarantined={quar_count}, dups={dup_count}"
        )

    # 2. Verify Quarantined Records against Expected Fixture
    with open(fixtures_dir / "expected_quarantine.json", "r", encoding="utf-8") as f:
        expected_quarantine = json.load(f)

    expected_q_map = {
        (item["source_table"], item["record_id"]): item["reason_code"]
        for item in expected_quarantine["quarantined_records"]
    }

    actual_q_map = {
        (q.source_table, q.record_id): q.reason_code
        for q in quarantines
    }

    assert actual_q_map == expected_q_map, f"Quarantine mismatch:\nActual: {actual_q_map}\nExpected: {expected_q_map}"

    # 3. Verify Deduplication
    assert dups["web_events"] == 1
    assert dups["fans"] == 0
    assert dups["orders"] == 0


def test_boundary_timestamps() -> None:
    validator = DataValidator(as_of_timestamp="2026-10-01T00:00:00Z")
    raw_data = {
        "fans": [{"fan_id": "FAN_B1", "created_at": "2026-10-01T00:00:00Z"}],  # Exact boundary: VALID
        "orders": [
            {
                "order_id": "ORD_B1",
                "fan_id": "FAN_B1",
                "order_status": "COMPLETED",
                "order_amount": "50.0",
                "order_timestamp": "2026-10-01T00:00:00Z",  # Exact boundary: VALID
            },
            {
                "order_id": "ORD_B2",
                "fan_id": "FAN_B1",
                "order_status": "COMPLETED",
                "order_amount": "50.0",
                "order_timestamp": "2026-10-01T00:00:01Z",  # 1 second in future: INVALID
            },
        ],
        "web_events": [],
        "email_events": [],
        "consent": [],
    }
    accepted, quarantines, _, _ = validator.validate_and_quarantine(raw_data)
    assert len(accepted["orders"]) == 1
    assert accepted["orders"][0]["order_id"] == "ORD_B1"
    assert len(quarantines) == 1
    assert quarantines[0].record_id == "ORD_B2"
    assert quarantines[0].reason_code == "INVALID_TIMESTAMP"
