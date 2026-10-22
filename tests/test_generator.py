"""
Tests for Synthetic Data Generator
Verifies seed determinism, defect injection tracking, and schema conformity.
"""

from src.generator.synthetic_data import SyntheticDataGenerator


def test_generator_determinism() -> None:
    """Verifies that identical seeds produce identical record counts and hashes."""
    gen1 = SyntheticDataGenerator(seed=123, defect_rate=0.01)
    data1, manifest1 = gen1.generate_dataset(num_fans=100, num_events=500, dataset_name="det_test")

    gen2 = SyntheticDataGenerator(seed=123, defect_rate=0.01)
    data2, manifest2 = gen2.generate_dataset(num_fans=100, num_events=500, dataset_name="det_test")

    assert manifest1.record_counts == manifest2.record_counts
    assert len(manifest1.injected_defects) == len(manifest2.injected_defects)

    for i in range(len(data1["fans"])):
        assert data1["fans"][i] == data2["fans"][i]

    for i in range(len(data1["orders"])):
        assert data1["orders"][i] == data2["orders"][i]


def test_generator_defect_tracking() -> None:
    """Verifies that injected defects are accurately recorded in the manifest."""
    gen = SyntheticDataGenerator(seed=999, defect_rate=0.05)
    data, manifest = gen.generate_dataset(num_fans=200, num_events=1000, dataset_name="defect_test")

    assert len(manifest.injected_defects) > 0
    categories = {d["defect_category"] for d in manifest.injected_defects}

    expected_categories = {
        "DUPLICATE_ID",
        "MISSING_REQUIRED_FIELD",
        "INVALID_TIMESTAMP",
        "UNKNOWN_FAN_REFERENCE",
        "INVALID_ORDER_AMOUNT",
        "INVALID_CONSENT_STATUS",
    }
    assert expected_categories.issubset(categories)


def test_generator_zero_defect_clean_run() -> None:
    """Verifies that setting defect_rate=0 creates zero injected defects."""
    gen = SyntheticDataGenerator(seed=42, defect_rate=0.0)
    data, manifest = gen.generate_dataset(num_fans=50, num_events=200, dataset_name="clean_test")

    assert len(manifest.injected_defects) == 0
    assert len(manifest.summary_by_defect_category) == 0
