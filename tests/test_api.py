"""
Tests for FastAPI Application
Tests health checks, fan profile lookup, segment membership queries,
consent filtering, pagination, and error responses.
"""

from fastapi.testclient import TestClient
import pytest

from src.api.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "Fan360 REST API"
    assert "not publicly production-hardened" in data["notice"]


def test_fan_profile_endpoint_found_and_not_found(client) -> None:
    # 1. Existing Fan (FAN_000001 from demo dataset loaded in DB)
    res = client.get("/fans/FAN_000001")
    if res.status_code == 200:
        data = res.json()
        assert data["fan_id"] == "FAN_000001"
        assert "country" in data
        assert "marketing_consent_status" in data
        assert isinstance(data["segment_memberships"], list)

    # 2. Non-existent Fan -> 404
    res404 = client.get("/fans/FAN_NONEXISTENT_999999")
    assert res404.status_code == 404
    assert "not found" in res404.json()["detail"].lower()


def test_segments_list_endpoint(client) -> None:
    res = client.get("/segments")
    assert res.status_code == 200
    segments = res.json()
    assert len(segments) >= 5
    codes = {s["segment_code"] for s in segments}
    assert "repeat_buyers" in codes
    assert "high_spending_buyers" in codes
    assert "engaged_non_buyers" in codes
    assert "inactive_fans" in codes
    assert "abandoned_cart" in codes


def test_segment_members_pagination_and_consent_filter(client) -> None:
    # Query repeat_buyers with limit=5
    res = client.get("/segments/repeat_buyers/members?limit=5&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert data["segment_code"] == "repeat_buyers"
    assert data["limit"] == 5
    assert len(data["items"]) <= 5

    # Query with activation_only=True
    res_act = client.get("/segments/repeat_buyers/members?activation_only=true&limit=10")
    assert res_act.status_code == 200
    act_data = res_act.json()
    for item in act_data["items"]:
        assert item["activation_eligible"] is True
        assert item["marketing_consent_status"] == "OPT_IN"

    # Test limit validation: limit > 100 should return 422 Unprocessable Entity
    res_invalid_limit = client.get("/segments/repeat_buyers/members?limit=150")
    assert res_invalid_limit.status_code == 422

    # Test non-existent segment -> 404
    res_bad_seg = client.get("/segments/unknown_segment_xyz/members")
    assert res_bad_seg.status_code == 404


def test_run_quality_endpoint(client) -> None:
    # Query recent runs list first
    runs_res = client.get("/runs?limit=1")
    assert runs_res.status_code == 200
    runs = runs_res.json()
    if runs:
        run_id = runs[0]["run_id"]
        res = client.get(f"/runs/{run_id}/quality")
        assert res.status_code == 200
        data = res.json()
        assert data["run_id"] == run_id
        assert data["reconciliation_status"] in ["BALANCED", "DISCREPANCY"]
        assert "quarantine_breakdown_by_reason" in data

    # 404 on bad run_id
    bad_res = client.get("/runs/RUN_DOES_NOT_EXIST/quality")
    assert bad_res.status_code == 404
