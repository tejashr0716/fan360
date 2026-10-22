"""
Fan360 FastAPI REST API
Provides endpoints for fan profiles, segment memberships, activation previews,
and pipeline quality audits with OpenAPI documentation.

NOTE: This is a local educational demonstration API and is not publicly production-hardened.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.pipeline.db_loader import DatabaseLoader
from src.ai.schema import ProposedSegment
from src.ai.provider import (
    AuthenticationError,
    ConfigurationError,
    ProviderPayloadError,
    ProviderRefusalError,
    ProviderTimeoutError,
    RateLimitError,
    get_llm_adapter,
)
from src.ai.evaluator import AudienceEvaluator

app = FastAPI(
    title="Fan360 — Motorsport Fan Data & Audience Segmentation API",
    description=(
        "Local educational demonstration API for querying motorsport fan profiles, "
        "audience segments, and data quality audits. "
        "Inspired by customer-data challenges in motorsport engagement."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

db_loader = DatabaseLoader()


# --- Pydantic Response Models ---

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str
    environment: str
    notice: str


class FanProfileResponse(BaseModel):
    fan_id: str
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    country: Optional[str]
    language: Optional[str]
    preferred_driver: Optional[str]
    created_at: Optional[str]
    last_activity_time: Optional[str]
    valid_completed_order_count: int
    total_valid_spend: float
    marketing_consent_status: str
    segment_memberships: List[Dict[str, Any]]


class SegmentSummary(BaseModel):
    segment_code: str
    segment_name: str
    description: Optional[str]
    total_qualified: int
    activation_eligible: int


class SegmentMemberItem(BaseModel):
    fan_id: str
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    marketing_consent_status: str
    activation_eligible: bool
    qualification_reason: str


class SegmentMembersResponse(BaseModel):
    segment_code: str
    activation_only: bool
    total_matching: int
    limit: int
    offset: int
    items: List[SegmentMemberItem]


class QualityAuditResponse(BaseModel):
    run_id: str
    dataset_name: str
    as_of_timestamp: str
    status: str
    reconciliation_status: str
    raw_records_count: int
    accepted_records_count: int
    quarantined_records_count: int
    duplicates_removed_count: int
    profiles_count: int
    memberships_count: int
    activation_count: int
    quarantine_breakdown_by_reason: Dict[str, int]
    audit_details: Optional[Dict[str, Any]]


# --- API Routes ---

@app.get("/health", response_model=HealthResponse, tags=["System"])
def get_health() -> HealthResponse:
    """System health check and database connectivity probe."""
    db_status = "connected"
    try:
        with db_loader.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
    except Exception as e:
        db_status = f"unavailable: {str(e)}"

    return HealthResponse(
        status="healthy" if "unavailable" not in db_status else "degraded",
        service="Fan360 REST API",
        version="1.0.0",
        database=db_status,
        environment="local-development",
        notice="Local educational demo only; not publicly production-hardened.",
    )


@app.get("/fans/{fan_id}", response_model=FanProfileResponse, tags=["Fans"])
def get_fan_profile(fan_id: str) -> FanProfileResponse:
    """Retrieves consolidated fan profile, spending history, consent, and current segment memberships."""
    sql_fan = """
        SELECT fan_id, first_name, last_name, email, country, language, preferred_driver,
               created_at, last_activity_time, valid_completed_order_count, total_valid_spend,
               marketing_consent_status
        FROM fan_profiles
        WHERE fan_id = %s;
    """
    sql_mem = """
        SELECT segment_code, qualifies, activation_eligible, reason
        FROM fan_segment_memberships
        WHERE fan_id = %s AND qualifies = 1;
    """
    try:
        with db_loader.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql_fan, (fan_id,))
                fan_row = cur.fetchone()
                if not fan_row:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Fan with ID '{fan_id}' was not found in the platform.",
                    )
                cur.execute(sql_mem, (fan_id,))
                memberships = cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return FanProfileResponse(
        fan_id=fan_row["fan_id"],
        first_name=fan_row["first_name"],
        last_name=fan_row["last_name"],
        email=fan_row["email"],
        country=fan_row["country"],
        language=fan_row["language"],
        preferred_driver=fan_row["preferred_driver"],
        created_at=fan_row["created_at"].isoformat() if fan_row["created_at"] else None,
        last_activity_time=fan_row["last_activity_time"].isoformat() if fan_row["last_activity_time"] else None,
        valid_completed_order_count=fan_row["valid_completed_order_count"] or 0,
        total_valid_spend=float(fan_row["total_valid_spend"] or 0.0),
        marketing_consent_status=fan_row["marketing_consent_status"] or "NONE",
        segment_memberships=[dict(m) for m in memberships],
    )


@app.get("/segments", response_model=List[SegmentSummary], tags=["Segments"])
def list_segments() -> List[SegmentSummary]:
    """Lists all configured audience segments with total qualified fans and consent-eligible activation size."""
    sql = """
        SELECT d.segment_code, d.segment_name, d.description,
               COALESCE(COUNT(m.fan_id) FILTER (WHERE m.qualifies = 1), 0) AS total_qualified,
               COALESCE(COUNT(m.fan_id) FILTER (WHERE m.qualifies = 1 AND m.activation_eligible = 1), 0) AS activation_eligible
        FROM segment_definitions d
        LEFT JOIN fan_segment_memberships m ON d.segment_code = m.segment_code
        GROUP BY d.segment_code, d.segment_name, d.description
        ORDER BY d.segment_name;
    """
    try:
        with db_loader.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    return [
        SegmentSummary(
            segment_code=r["segment_code"],
            segment_name=r["segment_name"],
            description=r["description"],
            total_qualified=r["total_qualified"],
            activation_eligible=r["activation_eligible"],
        )
        for r in rows
    ]


@app.get("/segments/{segment_name}/members", response_model=SegmentMembersResponse, tags=["Segments"])
def get_segment_members(
    segment_name: str,
    activation_only: bool = Query(
        False,
        description="Filter to fans with valid marketing consent (OPT_IN) eligible for campaign activation."
    ),
    limit: int = Query(20, ge=1, le=100, description="Page limit (max 100)"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> SegmentMembersResponse:
    """
    Lists fans belonging to a segment with pagination, qualification reasons,
    and optional consent-only activation filtering.
    """
    where_clauses = ["m.segment_code = %s", "m.qualifies = 1"]
    params: List[Any] = [segment_name]

    if activation_only:
        where_clauses.append("m.activation_eligible = 1")
        where_clauses.append("p.marketing_consent_status = 'OPT_IN'")

    where_sql = " AND ".join(where_clauses)

    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM fan_segment_memberships m
        JOIN fan_profiles p ON m.fan_id = p.fan_id
        WHERE {where_sql};
    """

    data_sql = f"""
        SELECT m.fan_id, p.first_name, p.last_name, p.email,
               p.marketing_consent_status, m.activation_eligible, m.reason
        FROM fan_segment_memberships m
        JOIN fan_profiles p ON m.fan_id = p.fan_id
        WHERE {where_sql}
        ORDER BY m.fan_id
        LIMIT %s OFFSET %s;
    """

    try:
        with db_loader.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check if segment exists
                cur.execute("SELECT 1 FROM segment_definitions WHERE segment_code = %s;", (segment_name,))
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Segment '{segment_name}' is not defined.",
                    )

                cur.execute(count_sql, tuple(params))
                total = cur.fetchone()["total"]

                cur.execute(data_sql, tuple(params + [limit, offset]))
                rows = cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    items = [
        SegmentMemberItem(
            fan_id=r["fan_id"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            email=r["email"],
            marketing_consent_status=r["marketing_consent_status"] or "NONE",
            activation_eligible=bool(r["activation_eligible"]),
            qualification_reason=r["reason"] or "",
        )
        for r in rows
    ]

    return SegmentMembersResponse(
        segment_code=segment_name,
        activation_only=activation_only,
        total_matching=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@app.get("/runs/{run_id}/quality", response_model=QualityAuditResponse, tags=["Quality & Audit"])
def get_run_quality(run_id: str) -> QualityAuditResponse:
    """Retrieves run-level data quality reconciliation, counts, and quarantine breakdown."""
    sql_run = "SELECT * FROM pipeline_runs WHERE run_id = %s;"
    sql_q = """
        SELECT reason_code, COUNT(*) AS count
        FROM quarantine_records
        WHERE run_id = %s
        GROUP BY reason_code
        ORDER BY count DESC;
    """
    try:
        with db_loader.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql_run, (run_id,))
                run_row = cur.fetchone()
                if not run_row:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Pipeline run '{run_id}' not found.",
                    )
                cur.execute(sql_q, (run_id,))
                q_rows = cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    q_map = {r["reason_code"]: r["count"] for r in q_rows}

    return QualityAuditResponse(
        run_id=run_row["run_id"],
        dataset_name=run_row["dataset_name"],
        as_of_timestamp=run_row["as_of_timestamp"].isoformat(),
        status=run_row["status"],
        reconciliation_status=run_row["reconciliation_status"],
        raw_records_count=run_row["raw_records_count"],
        accepted_records_count=run_row["accepted_records_count"],
        quarantined_records_count=run_row["quarantined_records_count"],
        duplicates_removed_count=run_row["duplicates_removed_count"],
        profiles_count=run_row["profiles_count"],
        memberships_count=run_row["memberships_count"],
        activation_count=run_row["activation_count"],
        quarantine_breakdown_by_reason=q_map,
        audit_details=run_row.get("audit_details"),
    )


@app.get("/runs", tags=["Quality & Audit"])
def list_runs(limit: int = 10) -> List[Dict[str, Any]]:
    """Lists recent pipeline execution runs."""
    sql = "SELECT run_id, dataset_name, started_at, completed_at, status, reconciliation_status FROM pipeline_runs ORDER BY started_at DESC LIMIT %s;"
    with db_loader.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (limit,))
            return [dict(r) for r in cur.fetchall()]


# --- AI Audience Builder Routes ---

class AIProposeRequest(BaseModel):
    query: str


class AIProposeResponse(BaseModel):
    proposal: ProposedSegment
    provider_mode: str


class AIPreviewRequest(BaseModel):
    segment: ProposedSegment
    limit: int = 10


ai_evaluator = AudienceEvaluator(db_loader)


@app.post("/ai/propose", response_model=AIProposeResponse, tags=["AI Audience Builder"])
def propose_audience(req: AIProposeRequest) -> AIProposeResponse:
    """
    Translates natural-language audience requirements into a validated, reviewable
    structured segment proposal using an LLM adapter.
    Does NOT query customer rows, execute SQL, or mutate database state.
    """
    try:
        adapter = get_llm_adapter()
        proposal, mode, metadata = adapter.interpret_request(req.query)
        return AIProposeResponse(proposal=proposal, provider_mode=mode)
    except ConfigurationError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM Configuration Error: {str(e)}",
        )
    except (AuthenticationError, RateLimitError, ProviderRefusalError, ProviderTimeoutError, ProviderPayloadError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Live LLM Provider Error: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"LLM interpretation error: {str(e)}")


@app.post("/ai/preview", tags=["AI Audience Builder"])
def preview_audience(req: AIPreviewRequest) -> Dict[str, Any]:
    """
    Revalidates the structured segment definition at preview time and safely executes
    read-only parameterized queries with mandatory consent segregation.
    Returns matched count vs consent-eligible count and sample profiles.
    """
    try:
        as_of_ts = db_loader.config.get("pipeline", {}).get("as_of_timestamp", "2026-10-01T00:00:00Z")
        result = ai_evaluator.evaluate_preview(
            segment=req.segment,
            as_of_timestamp=as_of_ts,
            preview_limit=req.limit,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Audience preview failed: {str(e)}")

