#!/usr/bin/env python3
"""
CLI Script to generate synthetic data for Fan360.
Usage:
    python scripts/generate_data.py --fans 10000 --events 100000 --seed 42 --error-rate 0.02 --out-dir data/raw
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generator.synthetic_data import SyntheticDataGenerator, export_dataset_to_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic data for Fan360.")
    parser.add_argument("--fans", type=int, default=10000, help="Number of fans to generate (default: 10000)")
    parser.add_argument("--events", type=int, default=100000, help="Total number of events to generate (default: 100000)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--error-rate", type=float, default=0.02, help="Defect injection rate (default: 0.02)")
    parser.add_argument("--as-of", type=str, default="2026-10-01T00:00:00Z", help="As-of reference timestamp")
    parser.add_argument("--dataset-name", type=str, default="demo_10k", help="Dataset name identifier")
    parser.add_argument("--out-dir", type=str, default="data/raw", help="Output directory for generated CSVs")

    args = parser.parse_args()

    print(f"Generating synthetic dataset '{args.dataset_name}' with {args.fans:,} fans, {args.events:,} events...")
    print(f"Seed: {args.seed}, Defect Rate: {args.error_rate * 100:.1f}%, Reference As-Of: {args.as_of}")

    generator = SyntheticDataGenerator(
        seed=args.seed,
        as_of_timestamp=args.as_of,
        defect_rate=args.error_rate,
    )

    data, manifest = generator.generate_dataset(
        num_fans=args.fans,
        num_events=args.events,
        dataset_name=args.dataset_name,
    )

    export_dataset_to_csv(data, manifest, args.out_dir)

    print("\nDataset generation complete!")
    print(f"Saved files to: {args.out_dir}")
    print("Table Record Counts:")
    for tbl, count in manifest.record_counts.items():
        print(f"  - {tbl}: {count:,} rows")
    print(f"Total Injected Defects: {len(manifest.injected_defects):,}")
    for cat, count in manifest.summary_by_defect_category.items():
        print(f"  - {cat}: {count:,}")
    print(f"Manifest saved to: {Path(args.out_dir) / 'generator_manifest.json'}")


if __name__ == "__main__":
    main()
