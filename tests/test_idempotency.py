"""
Tests for Pipeline Idempotency
Verifies that running the pipeline multiple times on identical input data
produces identical logical row counts and canonical SHA256 hashes of business outputs.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from src.pipeline.db_loader import DatabaseLoader
from src.pipeline.spark_pipeline import SparkFanPipeline, get_spark_session
from src.pipeline.validation import DataValidator


@pytest.fixture(scope="module")
def spark():
    return get_spark_session(app_name="Fan360-IdempotencyTest")


def compute_canonical_hash(records: List[Dict[str, Any]], key_fields: List[str]) -> str:
    """Computes deterministic SHA256 hash of sorted records excluding timestamps and run IDs."""
    normalized = []
    for r in records:
        item = {k: r[k] for k in key_fields if k in r}
        normalized.append(item)
    normalized.sort(key=lambda x: str([x.get(k) for k in key_fields]))
    serialized = json.dumps(normalized, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def test_idempotent_pipeline_execution(spark) -> None:
    # Use deterministic fixture data
    from tests.test_segments import load_fixture_csv
    fixtures_dir = Path("tests/fixtures")
    raw_data = {
        "fans": load_fixture_csv(fixtures_dir / "fans.csv"),
        "orders": load_fixture_csv(fixtures_dir / "orders.csv"),
        "web_events": load_fixture_csv(fixtures_dir / "web_events.csv"),
        "email_events": load_fixture_csv(fixtures_dir / "email_events.csv"),
        "consent": load_fixture_csv(fixtures_dir / "consent.csv"),
    }

    as_of = "2026-10-01T00:00:00Z"
    validator = DataValidator(as_of_timestamp=as_of)
    accepted, quarantines, dups, _ = validator.validate_and_quarantine(raw_data)

    pipeline = SparkFanPipeline(spark=spark, as_of_timestamp=as_of)

    # --- Run 1 ---
    prof1_df, mem1_df, act1_df = pipeline.process(accepted)
    prof1 = [r.asDict() for r in prof1_df.collect()]
    mem1 = [r.asDict() for r in mem1_df.collect()]
    act1 = [r.asDict() for r in act1_df.collect()]

    # --- Run 2 on identical inputs ---
    prof2_df, mem2_df, act2_df = pipeline.process(accepted)
    prof2 = [r.asDict() for r in prof2_df.collect()]
    mem2 = [r.asDict() for r in mem2_df.collect()]
    act2 = [r.asDict() for r in act2_df.collect()]

    # 1. Compare Row Counts
    assert len(prof1) == len(prof2), f"Profiles count mismatch: {len(prof1)} vs {len(prof2)}"
    assert len(mem1) == len(mem2), f"Memberships count mismatch: {len(mem1)} vs {len(mem2)}"
    assert len(act1) == len(act2), f"Activation count mismatch: {len(act1)} vs {len(act2)}"

    # 2. Compare Canonical Content Hashes (Excluding run_ids and processing timestamps)
    prof_hash1 = compute_canonical_hash(prof1, ["fan_id", "valid_completed_order_count", "total_valid_spend", "marketing_consent_status"])
    prof_hash2 = compute_canonical_hash(prof2, ["fan_id", "valid_completed_order_count", "total_valid_spend", "marketing_consent_status"])
    assert prof_hash1 == prof_hash2, "Fan profiles content hash mismatch between runs!"

    mem_hash1 = compute_canonical_hash(mem1, ["fan_id", "segment_code", "qualifies", "activation_eligible", "reason"])
    mem_hash2 = compute_canonical_hash(mem2, ["fan_id", "segment_code", "qualifies", "activation_eligible", "reason"])
    assert mem_hash1 == mem_hash2, "Segment memberships content hash mismatch between runs!"

    act_hash1 = compute_canonical_hash(act1, ["fan_id", "segment_code", "email", "consent_status"])
    act_hash2 = compute_canonical_hash(act2, ["fan_id", "segment_code", "email", "consent_status"])
    assert act_hash1 == act_hash2, "Activation audience content hash mismatch between runs!"


def test_database_idempotent_upsert(spark) -> None:
    """Verifies that inserting the same dataset twice into PostgreSQL does not duplicate primary keys or alter counts."""
    from tests.test_segments import load_fixture_csv
    fixtures_dir = Path("tests/fixtures")
    raw_data = {
        "fans": load_fixture_csv(fixtures_dir / "fans.csv"),
        "orders": load_fixture_csv(fixtures_dir / "orders.csv"),
        "web_events": load_fixture_csv(fixtures_dir / "web_events.csv"),
        "email_events": load_fixture_csv(fixtures_dir / "email_events.csv"),
        "consent": load_fixture_csv(fixtures_dir / "consent.csv"),
    }
    as_of = "2026-10-01T00:00:00Z"
    validator = DataValidator(as_of_timestamp=as_of)
    accepted, _, _, _ = validator.validate_and_quarantine(raw_data)

    pipeline = SparkFanPipeline(spark=spark, as_of_timestamp=as_of)
    prof_df, mem_df, _ = pipeline.process(accepted)

    db_loader = DatabaseLoader()
    db_loader.init_schema()

    # Initial load
    db_loader.load_profiles(prof_df, run_id="IDEM_RUN_1")
    db_loader.load_memberships(mem_df, run_id="IDEM_RUN_1")

    with db_loader.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fan_profiles;")
            count_prof_1 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM fan_segment_memberships;")
            count_mem_1 = cur.fetchone()[0]

    # Re-run load with same data
    db_loader.load_profiles(prof_df, run_id="IDEM_RUN_2")
    db_loader.load_memberships(mem_df, run_id="IDEM_RUN_2")

    with db_loader.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fan_profiles;")
            count_prof_2 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM fan_segment_memberships;")
            count_mem_2 = cur.fetchone()[0]

    assert count_prof_1 == count_prof_2, f"Logical row count changed in fan_profiles! {count_prof_1} vs {count_prof_2}"
    assert count_mem_1 == count_mem_2, f"Logical row count changed in fan_segment_memberships! {count_mem_1} vs {count_mem_2}"
