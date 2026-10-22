"""
End-to-End Pipeline Integration Test
Executes the full pipeline workflow from raw synthetic generation to PySpark processing,
PostgreSQL storage, and FastAPI REST response validation.
"""

import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from scripts.generate_data import SyntheticDataGenerator, export_dataset_to_csv
from scripts.run_pipeline import run_pipeline
from src.api.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_full_end_to_end_pipeline_and_api(client) -> None:
    temp_dir = tempfile.mkdtemp(prefix="fan360_e2e_")
    try:
        # 1. Generate small deterministic test dataset
        generator = SyntheticDataGenerator(seed=777, defect_rate=0.03)
        data, manifest = generator.generate_dataset(num_fans=150, num_events=600, dataset_name="e2e_test")
        export_dataset_to_csv(data, manifest, temp_dir)

        # 2. Run master pipeline
        e2e_run_id = "RUN_E2E_VERIFICATION"
        audit = run_pipeline(
            data_dir=temp_dir,
            dataset_name="e2e_test",
            as_of="2026-10-01T00:00:00Z",
            run_id=e2e_run_id,
            skip_db=False,
        )

        assert audit.status == "SUCCESS"
        assert audit.reconciliation_balanced is True
        assert audit.profiles_count == 150
        assert audit.memberships_count > 0

        # 3. Query API for run quality
        res_q = client.get(f"/runs/{e2e_run_id}/quality")
        assert res_q.status_code == 200
        q_data = res_q.json()
        assert q_data["reconciliation_status"] == "BALANCED"
        assert q_data["raw_records_count"] == audit.details["raw_total"]

        # 4. Query API for segments
        res_seg = client.get("/segments")
        assert res_seg.status_code == 200
        segments = res_seg.json()
        assert len(segments) >= 5

        # 5. Query API for fan profile
        res_fan = client.get("/fans/FAN_000001")
        assert res_fan.status_code == 200
        fan_data = res_fan.json()
        assert fan_data["fan_id"] == "FAN_000001"
        assert "country" in fan_data

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
