"""
Fan360 Validation and Quarantine Engine
Performs schema checks, field validation, referential integrity, deduplication,
and hierarchical non-double-counting quarantine assignment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from src.pipeline.schema import QuarantineRecord, ValidationResult


class DataValidator:
    """Validates records across sources and separates valid, duplicate, and quarantined rows."""

    def __init__(self, as_of_timestamp: str = "2026-10-01T00:00:00Z"):
        self.as_of_dt = datetime.fromisoformat(as_of_timestamp.replace("Z", "+00:00"))

    def _parse_timestamp(self, ts_str: Any) -> Optional[datetime]:
        if not ts_str or not isinstance(ts_str, str):
            return None
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def validate_and_quarantine(
        self,
        raw_data: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[
        Dict[str, List[Dict[str, Any]]],      # Accepted records
        List[QuarantineRecord],                # Quarantined records
        Dict[str, int],                        # Duplicates removed per source
        Dict[str, int],                        # Quarantined counts per source
    ]:
        """Validates all raw datasets and returns accepted records, quarantine records, and audit counts."""
        accepted: Dict[str, List[Dict[str, Any]]] = {}
        quarantine_records: List[QuarantineRecord] = []
        duplicates_removed: Dict[str, int] = {k: 0 for k in raw_data.keys()}
        quarantined_counts: Dict[str, int] = {k: 0 for k in raw_data.keys()}

        # Phase 1: Validate Fans First (Required for Referential Integrity)
        raw_fans = raw_data.get("fans", [])
        valid_fans: List[Dict[str, Any]] = []
        seen_fan_ids: Set[str] = set()

        for rec in raw_fans:
            fan_id = (rec.get("fan_id") or "").strip()
            if not fan_id:
                quarantine_records.append(QuarantineRecord(
                    source_table="fans",
                    record_id="UNKNOWN_FAN",
                    reason_code="MISSING_REQUIRED_FIELD",
                    raw_payload=rec,
                ))
                quarantined_counts["fans"] += 1
                continue

            if fan_id in seen_fan_ids:
                duplicates_removed["fans"] += 1
                continue

            ts = self._parse_timestamp(rec.get("created_at"))
            if ts is None or ts > self.as_of_dt:
                quarantine_records.append(QuarantineRecord(
                    source_table="fans",
                    record_id=fan_id,
                    reason_code="INVALID_TIMESTAMP",
                    raw_payload=rec,
                ))
                quarantined_counts["fans"] += 1
                continue

            seen_fan_ids.add(fan_id)
            valid_fans.append(rec)

        accepted["fans"] = valid_fans
        valid_fan_ids: Set[str] = seen_fan_ids

        # Phase 2: Validate Orders
        raw_orders = raw_data.get("orders", [])
        valid_orders: List[Dict[str, Any]] = []
        seen_order_ids: Set[str] = set()

        for rec in raw_orders:
            order_id = (rec.get("order_id") or "").strip()
            fan_id = (rec.get("fan_id") or "").strip()

            # Deduplication
            if order_id and order_id in seen_order_ids:
                duplicates_removed["orders"] += 1
                continue

            # Validation Hierarchy (Ensures non-double-counting)
            if not order_id or not fan_id or not rec.get("order_status"):
                quarantine_records.append(QuarantineRecord(
                    source_table="orders",
                    record_id=order_id or "UNKNOWN_ORDER",
                    reason_code="MISSING_REQUIRED_FIELD",
                    raw_payload=rec,
                ))
                quarantined_counts["orders"] += 1
                continue

            if fan_id not in valid_fan_ids:
                quarantine_records.append(QuarantineRecord(
                    source_table="orders",
                    record_id=order_id,
                    reason_code="UNKNOWN_FAN_REFERENCE",
                    raw_payload=rec,
                ))
                quarantined_counts["orders"] += 1
                continue

            ts = self._parse_timestamp(rec.get("order_timestamp"))
            if ts is None or ts > self.as_of_dt:
                quarantine_records.append(QuarantineRecord(
                    source_table="orders",
                    record_id=order_id,
                    reason_code="INVALID_TIMESTAMP",
                    raw_payload=rec,
                ))
                quarantined_counts["orders"] += 1
                continue

            try:
                amount = float(rec.get("order_amount", 0.0))
                if amount <= 0.0:
                    quarantine_records.append(QuarantineRecord(
                        source_table="orders",
                        record_id=order_id,
                        reason_code="INVALID_ORDER_AMOUNT",
                        raw_payload=rec,
                    ))
                    quarantined_counts["orders"] += 1
                    continue
            except (ValueError, TypeError):
                quarantine_records.append(QuarantineRecord(
                    source_table="orders",
                    record_id=order_id,
                    reason_code="INVALID_ORDER_AMOUNT",
                    raw_payload=rec,
                ))
                quarantined_counts["orders"] += 1
                continue

            seen_order_ids.add(order_id)
            valid_orders.append(rec)

        accepted["orders"] = valid_orders

        # Phase 3: Validate Web Events
        raw_web = raw_data.get("web_events", [])
        valid_web: List[Dict[str, Any]] = []
        seen_web_ids: Set[str] = set()

        for rec in raw_web:
            event_id = (rec.get("event_id") or "").strip()
            fan_id = (rec.get("fan_id") or "").strip()

            if event_id and event_id in seen_web_ids:
                duplicates_removed["web_events"] += 1
                continue

            if not event_id or not fan_id or not rec.get("event_type"):
                quarantine_records.append(QuarantineRecord(
                    source_table="web_events",
                    record_id=event_id or "UNKNOWN_EVENT",
                    reason_code="MISSING_REQUIRED_FIELD",
                    raw_payload=rec,
                ))
                quarantined_counts["web_events"] += 1
                continue

            if fan_id not in valid_fan_ids:
                quarantine_records.append(QuarantineRecord(
                    source_table="web_events",
                    record_id=event_id,
                    reason_code="UNKNOWN_FAN_REFERENCE",
                    raw_payload=rec,
                ))
                quarantined_counts["web_events"] += 1
                continue

            ts = self._parse_timestamp(rec.get("event_timestamp"))
            if ts is None or ts > self.as_of_dt:
                quarantine_records.append(QuarantineRecord(
                    source_table="web_events",
                    record_id=event_id,
                    reason_code="INVALID_TIMESTAMP",
                    raw_payload=rec,
                ))
                quarantined_counts["web_events"] += 1
                continue

            seen_web_ids.add(event_id)
            valid_web.append(rec)

        accepted["web_events"] = valid_web

        # Phase 4: Validate Email Events
        raw_email = raw_data.get("email_events", [])
        valid_email: List[Dict[str, Any]] = []
        seen_email_ids: Set[str] = set()

        for rec in raw_email:
            event_id = (rec.get("event_id") or "").strip()
            fan_id = (rec.get("fan_id") or "").strip()

            if event_id and event_id in seen_email_ids:
                duplicates_removed["email_events"] += 1
                continue

            if not event_id or not fan_id or not rec.get("action"):
                quarantine_records.append(QuarantineRecord(
                    source_table="email_events",
                    record_id=event_id or "UNKNOWN_EVENT",
                    reason_code="MISSING_REQUIRED_FIELD",
                    raw_payload=rec,
                ))
                quarantined_counts["email_events"] += 1
                continue

            if fan_id not in valid_fan_ids:
                quarantine_records.append(QuarantineRecord(
                    source_table="email_events",
                    record_id=event_id,
                    reason_code="UNKNOWN_FAN_REFERENCE",
                    raw_payload=rec,
                ))
                quarantined_counts["email_events"] += 1
                continue

            ts = self._parse_timestamp(rec.get("event_timestamp"))
            if ts is None or ts > self.as_of_dt:
                quarantine_records.append(QuarantineRecord(
                    source_table="email_events",
                    record_id=event_id,
                    reason_code="INVALID_TIMESTAMP",
                    raw_payload=rec,
                ))
                quarantined_counts["email_events"] += 1
                continue

            seen_email_ids.add(event_id)
            valid_email.append(rec)

        accepted["email_events"] = valid_email

        # Phase 5: Validate Consent Updates
        raw_consent = raw_data.get("consent", [])
        valid_consent: List[Dict[str, Any]] = []
        seen_consent_ids: Set[str] = set()

        for rec in raw_consent:
            consent_id = (rec.get("consent_id") or "").strip()
            fan_id = (rec.get("fan_id") or "").strip()
            status = (rec.get("status") or "").strip().upper()

            if consent_id and consent_id in seen_consent_ids:
                duplicates_removed["consent"] += 1
                continue

            if not consent_id or not fan_id:
                quarantine_records.append(QuarantineRecord(
                    source_table="consent",
                    record_id=consent_id or "UNKNOWN_CONSENT",
                    reason_code="MISSING_REQUIRED_FIELD",
                    raw_payload=rec,
                ))
                quarantined_counts["consent"] += 1
                continue

            if fan_id not in valid_fan_ids:
                quarantine_records.append(QuarantineRecord(
                    source_table="consent",
                    record_id=consent_id,
                    reason_code="UNKNOWN_FAN_REFERENCE",
                    raw_payload=rec,
                ))
                quarantined_counts["consent"] += 1
                continue

            ts = self._parse_timestamp(rec.get("update_timestamp"))
            if ts is None or ts > self.as_of_dt:
                quarantine_records.append(QuarantineRecord(
                    source_table="consent",
                    record_id=consent_id,
                    reason_code="INVALID_TIMESTAMP",
                    raw_payload=rec,
                ))
                quarantined_counts["consent"] += 1
                continue

            if status not in {"OPT_IN", "OPT_OUT"}:
                quarantine_records.append(QuarantineRecord(
                    source_table="consent",
                    record_id=consent_id,
                    reason_code="INVALID_CONSENT_STATUS",
                    raw_payload=rec,
                ))
                quarantined_counts["consent"] += 1
                continue

            seen_consent_ids.add(consent_id)
            valid_consent.append(rec)

        accepted["consent"] = valid_consent

        return accepted, quarantine_records, duplicates_removed, quarantined_counts
