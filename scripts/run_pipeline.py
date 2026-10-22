#!/usr/bin/env python3
"""
Master Pipeline Runner for Fan360
Executes ingestion, schema validation, quarantine, PySpark transformation,
audience calculation, idempotent database loading, and reconciliation auditing.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.db_loader import DatabaseLoader
from src.pipeline.schema import RunAudit
from src.pipeline.spark_pipeline import SparkFanPipeline, get_spark_session
from src.pipeline.validation import DataValidator


def load_table_csv(file_path: Path) -> List[Dict[str, Any]]:
    if not file_path.exists():
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def run_pipeline(
    data_dir: str = "data/raw",
    dataset_name: str = "demo_10k",
    as_of: str = "2026-10-01T00:00:00Z",
    run_id: str | None = None,
    skip_db: bool = False,
) -> RunAudit:
    run_id = run_id or f"RUN_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    start_time = datetime.now(timezone.utc)
    started_at_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"\n========================================================")
    print(f"Starting Fan360 Pipeline Run: {run_id}")
    print(f"Dataset: {dataset_name} | Source Dir: {data_dir}")
    print(f"Reference As-Of Timestamp: {as_of}")
    print(f"========================================================\n")

    in_path = Path(data_dir)
    raw_data = {
        "fans": load_table_csv(in_path / "fans.csv"),
        "orders": load_table_csv(in_path / "orders.csv"),
        "web_events": load_table_csv(in_path / "web_events.csv"),
        "email_events": load_table_csv(in_path / "email_events.csv"),
        "consent": load_table_csv(in_path / "consent.csv"),
    }

    raw_counts = {k: len(v) for k, v in raw_data.items()}
    total_raw = sum(raw_counts.values())
    print(f"Phase 1: Ingestion — Loaded {total_raw:,} total raw rows across 5 tables:")
    for k, v in raw_counts.items():
        print(f"  - {k}: {v:,} rows")

    # Phase 2: Validation & Quarantine
    print(f"\nPhase 2: Data Quality Validation & Deduplication...")
    validator = DataValidator(as_of_timestamp=as_of)
    accepted_data, quarantines, dups, quarantined_counts = validator.validate_and_quarantine(raw_data)

    accepted_counts = {k: len(v) for k, v in accepted_data.items()}
    total_accepted = sum(accepted_counts.values())
    total_quarantined = len(quarantines)
    total_dups = sum(dups.values())

    print(f"  - Accepted rows: {total_accepted:,}")
    print(f"  - Quarantined rows: {total_quarantined:,}")
    print(f"  - Duplicates removed: {total_dups:,}")

    # Check reconciliation
    reconciliation_balanced = True
    for tbl in raw_data.keys():
        diff = raw_counts[tbl] - (accepted_counts[tbl] + quarantined_counts[tbl] + dups[tbl])
        if diff != 0:
            reconciliation_balanced = False
            print(f"  [ERROR] Reconciliation discrepancy in {tbl}: diff={diff}")

    if reconciliation_balanced:
        print("  [SUCCESS] Reconciliation Check: 100% BALANCED (Raw = Accepted + Quarantined + Duplicates).")

    # Phase 3: PySpark Transformation & Audience Calculation
    print(f"\nPhase 3: PySpark Transformations & Segment Calculations...")
    spark = get_spark_session(app_name="Fan360-RunPipeline")
    pipeline = SparkFanPipeline(spark=spark, as_of_timestamp=as_of)
    profiles_df, memberships_df, activation_df = pipeline.process(accepted_data)

    profiles_count = profiles_df.count()
    memberships_count = memberships_df.filter("qualifies = 1").count()
    activation_count = activation_df.count()

    print(f"  - Consolidated Fan Profiles: {profiles_count:,}")
    print(f"  - Total Segment Qualifications: {memberships_count:,}")
    print(f"  - Consent-Eligible Activation Audiences: {activation_count:,}")

    # Segment Breakdown
    seg_breakdown = (
        memberships_df.filter("qualifies = 1")
        .groupBy("segment_code")
        .agg(
            {"fan_id": "count", "activation_eligible": "sum"}
        )
        .collect()
    )
    print("  Segment Distribution:")
    for row in seg_breakdown:
        s_code = row["segment_code"]
        total_qual = row["count(fan_id)"]
        act_elig = row["sum(activation_eligible)"]
        print(f"    * {s_code}: {total_qual:,} fans qualified ({act_elig:,} consent-eligible)")

    # Phase 4: Database Loading
    if not skip_db:
        print(f"\nPhase 4: Idempotent Loading into PostgreSQL...")
        db_loader = DatabaseLoader()
        db_loader.init_schema()
        db_loader.sync_segment_definitions()
        prof_loaded = db_loader.load_profiles(profiles_df, run_id)
        mem_loaded = db_loader.load_memberships(memberships_df, run_id)
        act_loaded = db_loader.load_activation_audiences(activation_df, run_id)
        quar_loaded = db_loader.load_quarantine_records(quarantines, run_id)
        print(f"  - Loaded {prof_loaded:,} profiles, {mem_loaded:,} memberships, "
              f"{act_loaded:,} activations, {quar_loaded:,} quarantines.")
    else:
        print("\nPhase 4: Database loading skipped (--skip-db set).")

    end_time = datetime.now(timezone.utc)
    completed_at_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    duration_sec = round((end_time - start_time).total_seconds(), 2)

    # Detailed Audit & Reconciliation Record
    audit = RunAudit(
        run_id=run_id,
        dataset_name=dataset_name,
        as_of_timestamp=as_of,
        started_at=started_at_str,
        completed_at=completed_at_str,
        status="SUCCESS",
        raw_counts=raw_counts,
        accepted_counts=accepted_counts,
        quarantined_counts=quarantined_counts,
        deduplicated_counts=dups,
        profiles_count=profiles_count,
        memberships_count=memberships_count,
        activation_count=activation_count,
        reconciliation_balanced=reconciliation_balanced,
        details={
            "duration_seconds": duration_sec,
            "raw_total": total_raw,
            "accepted_total": total_accepted,
            "quarantined_total": total_quarantined,
            "duplicates_total": total_dups,
        },
    )

    if not skip_db:
        db_loader.record_run_audit(audit)

    print(f"\nPipeline Run Completed in {duration_sec}s! Status: SUCCESS.")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Fan360 Ingestion and Audience Segmentation Pipeline.")
    parser.add_argument("--data-dir", type=str, default="data/raw", help="Path to raw CSV dataset directory")
    parser.add_argument("--dataset-name", type=str, default="demo_10k", help="Dataset identifier")
    parser.add_argument("--as-of", type=str, default="2026-10-01T00:00:00Z", help="Reference as-of timestamp")
    parser.add_argument("--run-id", type=str, default=None, help="Custom run ID")
    parser.add_argument("--skip-db", action="store_true", help="Skip database persistence")

    args = parser.parse_args()
    run_pipeline(
        data_dir=args.data_dir,
        dataset_name=args.dataset_name,
        as_of=args.as_of,
        run_id=args.run_id,
        skip_db=args.skip_db,
    )


if __name__ == "__main__":
    main()
