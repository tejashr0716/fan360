"""
Fan360 Deterministic Audience Evaluator & Consent Engine
Re-validates proposed segment definitions, builds parameterized SQL queries,
and enforces mandatory consent segregation (Matched vs Consent-Eligible).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from psycopg2.extras import RealDictCursor

from src.ai.schema import ProposedSegment, SegmentFilter
from src.pipeline.db_loader import DatabaseLoader


SQL_OPERATOR_MAP = {
    ">=": ">=",
    ">": ">",
    "==": "=",
    "<=": "<=",
    "<": "<",
    "!=": "!=",
}


class AudienceEvaluator:
    """Safely evaluates structured segment definitions against PostgreSQL fan_profiles."""

    def __init__(self, db_loader: DatabaseLoader):
        self.db = db_loader

    def build_where_clause(
        self,
        filters: List[SegmentFilter],
        as_of_timestamp: str = "2026-10-01T00:00:00Z",
    ) -> Tuple[str, List[Any]]:
        """
        Builds safe, parameterized WHERE clauses for allowlisted profile attributes.
        Returns SQL condition string and parameter values list.
        """
        clauses = []
        params = []

        for f in filters:
            if f.field == "days_since_last_activity":
                # Compute floor((as_of - last_activity_time) / 86400)
                sql_op = SQL_OPERATOR_MAP.get(f.operator, "=")
                clause = (
                    f"FLOOR(EXTRACT(EPOCH FROM (%s::timestamptz - COALESCE(last_activity_time, created_at))) / 86400) "
                    f"{sql_op} %s"
                )
                clauses.append(clause)
                params.extend([as_of_timestamp, f.value])

            elif f.operator == "in":
                # Parameterized IN list
                placeholders = ", ".join(["%s"] * len(f.value))
                clauses.append(f"{f.field} IN ({placeholders})")
                params.extend(f.value)

            else:
                sql_op = SQL_OPERATOR_MAP.get(f.operator, "=")
                clauses.append(f"{f.field} {sql_op} %s")
                params.append(f.value)

        where_str = " AND ".join(clauses) if clauses else "1=1"
        return where_str, params

    def evaluate_preview(
        self,
        segment: ProposedSegment,
        as_of_timestamp: str = "2026-10-01T00:00:00Z",
        preview_limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Executes read-only parameterized queries to calculate:
        1. Behavioral matched profiles count
        2. Consent-eligible activation count (strictly OPT_IN)
        3. A bounded preview of matching profiles
        """
        # 1. Preview-time revalidation: re-instantiate through Pydantic to catch any malicious edits
        validated_segment = ProposedSegment(**segment.model_dump())

        if validated_segment.clarification_required:
            return {
                "segment_name": validated_segment.name,
                "clarification_required": True,
                "clarification_question": validated_segment.clarification_question,
                "total_matched": 0,
                "consent_eligible": 0,
                "preview_profiles": [],
            }

        # 2. Build parameterized filter conditions
        where_sql, params = self.build_where_clause(validated_segment.filters, as_of_timestamp)

        # 3. Query behavioral total matches
        sql_total_matched = f"""
            SELECT COUNT(*) AS total
            FROM fan_profiles
            WHERE {where_sql};
        """

        # 4. Query consent-eligible matches (MANDATORY application logic: strictly marketing_consent_status = 'OPT_IN')
        sql_consent_eligible = f"""
            SELECT COUNT(*) AS eligible
            FROM fan_profiles
            WHERE ({where_sql}) AND marketing_consent_status = 'OPT_IN';
        """

        # 5. Query bounded sample preview
        sql_preview = f"""
            SELECT fan_id, first_name, last_name, email, country, language, preferred_driver,
                   valid_completed_order_count, total_valid_spend, marketing_consent_status,
                   (marketing_consent_status = 'OPT_IN') AS activation_eligible
            FROM fan_profiles
            WHERE {where_sql}
            ORDER BY fan_id
            LIMIT %s;
        """

        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Count total matching
                cur.execute(sql_total_matched, params)
                total_matched = cur.fetchone()["total"]

                # Count consent-eligible
                cur.execute(sql_consent_eligible, params)
                consent_eligible = cur.fetchone()["eligible"]

                # Fetch sample preview
                cur.execute(sql_preview, params + [preview_limit])
                raw_preview = cur.fetchall()

        preview_profiles = []
        for r in raw_preview:
            preview_profiles.append({
                "fan_id": r["fan_id"],
                "name": f"{r['first_name']} {r['last_name']}",
                "email": r["email"],
                "country": r["country"],
                "preferred_driver": r["preferred_driver"],
                "orders_count": r["valid_completed_order_count"],
                "total_spend": float(r["total_valid_spend"] or 0.0),
                "marketing_consent": r["marketing_consent_status"],
                "activation_eligible": bool(r["activation_eligible"]),
            })

        return {
            "segment_name": validated_segment.name,
            "clarification_required": False,
            "clarification_question": None,
            "filters_applied": [f.model_dump() for f in validated_segment.filters],
            "total_matched": total_matched,
            "consent_eligible": consent_eligible,
            "preview_limit": preview_limit,
            "preview_profiles": preview_profiles,
        }
