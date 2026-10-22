"""
Tests for Audience Segmentation & PySpark Transformation
Compares PySpark pipeline output on the golden fixture dataset against hand-authored expected memberships.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from src.pipeline.spark_pipeline import SparkFanPipeline, get_spark_session
from src.pipeline.validation import DataValidator


@pytest.fixture(scope="module")
def spark():
    s = get_spark_session(app_name="Fan360-Test")
    yield s


def load_fixture_csv(file_path: Path) -> List[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def test_segment_exact_matches_fixture(spark) -> None:
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

    pipeline = SparkFanPipeline(
        spark=spark,
        config_path="config/config.yaml",
        rules_path="config/segment_rules.yaml",
        as_of_timestamp="2026-10-01T00:00:00Z",
    )

    profiles_df, memberships_df, activation_df = pipeline.process(accepted)

    actual_memberships = [row.asDict() for row in memberships_df.collect()]
    actual_activation = [row.asDict() for row in activation_df.collect()]
    actual_profiles = {row["fan_id"]: row.asDict() for row in profiles_df.collect()}

    # 1. Load independently hand-authored expected memberships
    with open(fixtures_dir / "expected_memberships.json", "r", encoding="utf-8") as f:
        expected_segments = json.load(f)

    # 2. Check each segment's exact qualification set
    for segment_code, expected_fans in expected_segments.items():
        expected_fan_ids = {item["fan_id"] for item in expected_fans}
        actual_segment_members = {
            m["fan_id"]
            for m in actual_memberships
            if m["segment_code"] == segment_code and m["qualifies"] == 1
        }
        assert actual_segment_members == expected_fan_ids, (
            f"Segment '{segment_code}' qualification mismatch!\n"
            f"Actual: {actual_segment_members}\n"
            f"Expected: {expected_fan_ids}"
        )

        # Check activation eligibility flag
        expected_eligible = {item["fan_id"] for item in expected_fans if item["activation_eligible"]}
        actual_eligible = {
            m["fan_id"]
            for m in actual_memberships
            if m["segment_code"] == segment_code and m["activation_eligible"] == 1
        }
        assert actual_eligible == expected_eligible, (
            f"Segment '{segment_code}' activation eligibility mismatch!\n"
            f"Actual eligible: {actual_eligible}\n"
            f"Expected eligible: {expected_eligible}"
        )

    # 3. Verify that Abandoned Cart correctly resolves completed orders
    # FAN_005 had an add_to_cart for CART_RESOLVED_01 and completed order ORD_005 for that cart.
    # Must NOT be in abandoned_cart!
    cart_members = {
        m["fan_id"] for m in actual_memberships
        if m["segment_code"] == "abandoned_cart" and m["qualifies"] == 1
    }
    assert "FAN_005" not in cart_members, "FAN_005 had a resolving purchase and must not qualify for abandoned_cart"
    assert "FAN_004" in cart_members, "FAN_004 had an unresolved cart and must qualify for abandoned_cart"


def test_spend_and_order_count_aggregation(spark) -> None:
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
    profiles_df, _, _ = pipeline.process(accepted)
    profiles = {row["fan_id"]: row.asDict() for row in profiles_df.collect()}

    # FAN_001 had orders: $150, $120, $80 = $350.00, count = 3
    assert profiles["FAN_001"]["valid_completed_order_count"] == 3
    assert abs(profiles["FAN_001"]["total_valid_spend"] - 350.00) < 1e-4

    # FAN_002 had 0 orders = $0.00, count = 0
    assert profiles["FAN_002"]["valid_completed_order_count"] == 0
    assert abs(profiles["FAN_002"]["total_valid_spend"] - 0.0) < 1e-4
