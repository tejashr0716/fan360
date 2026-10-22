"""
Tests for Consent Safety & Resolution Logic
Verifies latest-effective-update resolution, deterministic tie-breakers,
strict exclusion of non-consenting fans from activation exports, and withdrawal handling.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List

import pytest
from src.pipeline.spark_pipeline import SparkFanPipeline, get_spark_session
from src.pipeline.validation import DataValidator


@pytest.fixture(scope="module")
def spark():
    s = get_spark_session(app_name="Fan360-ConsentTest")
    yield s


def load_fixture_csv(file_path: Path) -> List[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def test_consent_latest_effective_and_withdrawal(spark) -> None:
    fixtures_dir = Path("tests/fixtures")
    raw_data = {
        "fans": load_fixture_csv(fixtures_dir / "fans.csv"),
        "orders": load_fixture_csv(fixtures_dir / "orders.csv"),
        "web_events": load_fixture_csv(fixtures_dir / "web_events.csv"),
        "email_events": load_fixture_csv(fixtures_dir / "email_events.csv"),
        "consent": load_fixture_csv(fixtures_dir / "consent.csv"),
    }

    validator = DataValidator(as_of_timestamp="2026-10-01T00:00:00Z")
    accepted, _, _, _ = validator.validate_and_quarantine(raw_data)

    pipeline = SparkFanPipeline(spark=spark, as_of_timestamp="2026-10-01T00:00:00Z")
    profiles_df, memberships_df, activation_df = pipeline.process(accepted)

    profiles = {row["fan_id"]: row.asDict() for row in profiles_df.collect()}
    activation_records = [row.asDict() for row in activation_df.collect()]

    # 1. FAN_008 had conflicting updates: OPT_IN at t=1, OPT_OUT at t=2.
    # Latest resolved status must be OPT_OUT.
    assert profiles["FAN_008"]["marketing_consent_status"] == "OPT_OUT"

    # 2. FAN_009 was OPT_IN, then withdrew consent (OPT_OUT) on 2026-09-28.
    # Latest resolved status must be OPT_OUT.
    assert profiles["FAN_009"]["marketing_consent_status"] == "OPT_OUT"

    # 3. FAN_010 had NO consent records.
    # Missing consent must NOT imply permission (status = NONE).
    assert profiles["FAN_010"]["marketing_consent_status"] == "NONE"

    # 4. Strict Safety: ZERO non-consenting fans in activation export!
    activation_fan_ids = {rec["fan_id"] for rec in activation_records}
    for fan_id in activation_fan_ids:
        assert profiles[fan_id]["marketing_consent_status"] == "OPT_IN", (
            f"Fan {fan_id} has non-consenting status "
            f"'{profiles[fan_id]['marketing_consent_status']}' but appeared in activation audience!"
        )

    # Specific check: FAN_003, FAN_006, FAN_008, FAN_009, FAN_010 must NEVER appear in activation export
    forbidden_fans = {"FAN_003", "FAN_006", "FAN_008", "FAN_009", "FAN_010"}
    intersection = activation_fan_ids.intersection(forbidden_fans)
    assert len(intersection) == 0, f"Found non-consenting fans in activation audience: {intersection}"

    # 5. Descriptive profiles still exist and are accessible for these fans
    for f_id in forbidden_fans:
        assert f_id in profiles, f"Fan {f_id} should still have a descriptive fan profile"


def test_consent_withdrawal_dynamic_update(spark) -> None:
    """Verifies that withdrawing consent removes the fan from subsequent activation runs."""
    as_of = "2026-10-01T00:00:00Z"
    validator = DataValidator(as_of_timestamp=as_of)

    # Base dataset where FAN_W1 is OPT_IN
    raw_data = {
        "fans": [{"fan_id": "FAN_W1", "first_name": "Test", "last_name": "Fan", "email": "w1@test.com", "country": "GBR", "language": "en", "preferred_driver": "Elena Vance", "created_at": "2026-01-01T10:00:00Z"}],
        "orders": [
            {"order_id": "ORD_W1", "fan_id": "FAN_W1", "order_status": "COMPLETED", "order_amount": "100.0", "currency": "USD", "order_timestamp": "2026-06-01T10:00:00Z", "items_count": "1", "cart_id": ""},
            {"order_id": "ORD_W2", "fan_id": "FAN_W1", "order_status": "COMPLETED", "order_amount": "150.0", "currency": "USD", "order_timestamp": "2026-07-01T10:00:00Z", "items_count": "1", "cart_id": ""},
        ],
        "web_events": [],
        "email_events": [],
        "consent": [
            {"consent_id": "CNS_W1", "fan_id": "FAN_W1", "consent_type": "marketing_email", "status": "OPT_IN", "update_timestamp": "2026-01-01T10:05:00Z", "channel": "web_form"}
        ],
    }

    pipeline = SparkFanPipeline(spark=spark, as_of_timestamp=as_of)
    accepted, _, _, _ = validator.validate_and_quarantine(raw_data)
    _, _, act1 = pipeline.process(accepted)
    assert act1.filter(act1["fan_id"] == "FAN_W1").count() > 0, "FAN_W1 should be in activation audience when OPT_IN"

    # Now add withdrawal record
    raw_data["consent"].append(
        {"consent_id": "CNS_W2", "fan_id": "FAN_W1", "consent_type": "marketing_email", "status": "OPT_OUT", "update_timestamp": "2026-09-01T10:00:00Z", "channel": "unsubscribe_link"}
    )
    accepted2, _, _, _ = validator.validate_and_quarantine(raw_data)
    _, _, act2 = pipeline.process(accepted2)
    assert act2.filter(act2["fan_id"] == "FAN_W1").count() == 0, "FAN_W1 must be immediately removed from activation audience upon consent withdrawal"
