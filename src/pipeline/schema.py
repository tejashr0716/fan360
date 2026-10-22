"""
Fan360 Schema Definitions and Data Types
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ValidationResult:
    is_valid: bool
    primary_reason: Optional[str] = None
    all_reasons: List[str] = None

    def __post_init__(self):
        if self.all_reasons is None:
            self.all_reasons = []


@dataclass
class QuarantineRecord:
    source_table: str
    record_id: str
    reason_code: str
    raw_payload: Dict[str, Any]


@dataclass
class RunAudit:
    run_id: str
    dataset_name: str
    as_of_timestamp: str
    started_at: str
    completed_at: str
    status: str
    raw_counts: Dict[str, int]
    accepted_counts: Dict[str, int]
    quarantined_counts: Dict[str, int]
    deduplicated_counts: Dict[str, int]
    profiles_count: int
    memberships_count: int
    activation_count: int
    reconciliation_balanced: bool
    details: Dict[str, Any]
