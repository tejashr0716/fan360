"""
Fan360 AI Audience Requirement Schema
Defines strict Pydantic models for natural-language segment proposals.
Rejects unknown fields, unsupported operators, non-finite numbers, type mismatches, and extra properties.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Allowlisted fields derived strictly from fan_profiles schema and documented business rules
ALLOWLISTED_FIELDS = {
    "valid_completed_order_count": {
        "type": int,
        "description": "Total number of completed merchandise purchases.",
        "supported_operators": [">=", ">", "==", "<=", "<", "!="],
        "min_value": 0,
        "max_value": 100000,
    },
    "total_valid_spend": {
        "type": (int, float),
        "description": "Accumulated dollar spend on completed merchandise purchases (USD).",
        "supported_operators": [">=", ">", "<=", "<"],
        "min_value": 0.0,
        "max_value": 10000000.0,
    },
    "country": {
        "type": str,
        "description": "Three-letter ISO country code (e.g. USA, GBR, FRA, BRA, DEU).",
        "supported_operators": ["==", "!=", "in"],
        "max_length": 3,
    },
    "language": {
        "type": str,
        "description": "Two-letter ISO language code (e.g. en, fr, es, de, pt).",
        "supported_operators": ["==", "!=", "in"],
        "max_length": 2,
    },
    "preferred_driver": {
        "type": str,
        "description": "Fictional driver name (e.g. Lucas Rossi, Elena Vance, Marcus Sterling).",
        "supported_operators": ["==", "!="],
        "max_length": 64,
    },
    "days_since_last_activity": {
        "type": int,
        "description": "Days since last web event, email interaction, or order.",
        "supported_operators": [">", ">=", "<=", "<"],
        "min_value": 0,
        "max_value": 36500,
    },
}

SUPPORTED_OPERATORS = [">=", ">", "==", "<=", "<", "!=", "in"]


class SegmentFilter(BaseModel):
    """Represents a single allowlisted attribute filter with explicit AND semantics."""
    model_config = ConfigDict(extra="forbid")

    field: str = Field(..., description="Allowlisted profile attribute name.")
    operator: str = Field(..., description="Comparison operator (e.g. '>=', '==', 'in').")
    value: Union[int, float, str, List[str]] = Field(..., description="Typed filter argument.")

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        clean_field = v.strip().lower()
        if clean_field not in ALLOWLISTED_FIELDS:
            raise ValueError(
                f"Field '{v}' is not supported. Supported allowlisted fields are: "
                f"{', '.join(sorted(ALLOWLISTED_FIELDS.keys()))}"
            )
        return clean_field

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        clean_op = v.strip()
        if clean_op not in SUPPORTED_OPERATORS:
            raise ValueError(
                f"Operator '{v}' is unsupported. Supported operators are: {SUPPORTED_OPERATORS}"
            )
        return clean_op

    @model_validator(mode="after")
    def validate_field_operator_and_type(self) -> SegmentFilter:
        field_meta = ALLOWLISTED_FIELDS.get(self.field)
        if not field_meta:
            return self

        # Validate operator support for this specific field
        if self.operator not in field_meta["supported_operators"]:
            raise ValueError(
                f"Operator '{self.operator}' is not supported for field '{self.field}'. "
                f"Supported: {field_meta['supported_operators']}"
            )

        # Validate value type & finite values
        expected_type = field_meta["type"]
        if self.operator == "in":
            if not isinstance(self.value, list) or not all(isinstance(x, str) for x in self.value):
                raise ValueError(f"Operator 'in' for field '{self.field}' requires a list of strings.")
            if len(self.value) == 0:
                raise ValueError("List for 'in' operator cannot be empty.")
            if len(self.value) > 10:
                raise ValueError("List for 'in' operator cannot exceed 10 items.")
            for item in self.value:
                if len(item.strip()) == 0 or len(item) > field_meta.get("max_length", 64):
                    raise ValueError(f"Invalid string length in list for field '{self.field}'.")
        else:
            if expected_type == (int, float):
                if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
                    raise ValueError(f"Value for numeric field '{self.field}' must be a number.")
                if not math.isfinite(self.value):
                    raise ValueError(f"Value for numeric field '{self.field}' must be a finite number (not NaN or Inf).")
                min_v = field_meta.get("min_value", 0.0)
                max_v = field_meta.get("max_value", 1e9)
                if self.value < min_v or self.value > max_v:
                    raise ValueError(f"Value {self.value} for field '{self.field}' is outside valid range [{min_v}, {max_v}].")

            elif expected_type == int:
                if not isinstance(self.value, int) or isinstance(self.value, bool):
                    raise ValueError(f"Value for integer field '{self.field}' must be an integer.")
                min_v = field_meta.get("min_value", 0)
                max_v = field_meta.get("max_value", 1000000)
                if self.value < min_v or self.value > max_v:
                    raise ValueError(f"Value {self.value} for field '{self.field}' is outside valid range [{min_v}, {max_v}].")

            elif expected_type == str:
                if not isinstance(self.value, str):
                    raise ValueError(f"Value for field '{self.field}' must be a string.")
                clean_str = self.value.strip()
                if len(clean_str) == 0:
                    raise ValueError(f"Value for field '{self.field}' cannot be empty.")
                max_len = field_meta.get("max_length", 128)
                if len(clean_str) > max_len:
                    raise ValueError(f"Value for field '{self.field}' exceeds max length of {max_len} characters.")

        return self


class ProposedSegment(BaseModel):
    """Structured segment proposal generated from natural language."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., max_length=64, description="Short descriptive segment title.")
    description: str = Field(..., max_length=256, description="Human-readable business summary.")
    filters: List[SegmentFilter] = Field(
        default_factory=list,
        max_length=5,
        description="List of conjunctive (AND) filters.",
    )
    explanation: str = Field(..., max_length=512, description="How the natural language request maps to filters.")
    clarification_required: bool = Field(
        default=False,
        description="True if request is ambiguous or references undefined business thresholds.",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Question to present to the user when clarification is required.",
    )

    @field_validator("name", "description", "explanation")
    @classmethod
    def reject_empty_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only.")
        return v.strip()

    @model_validator(mode="after")
    def validate_clarification_logic(self) -> ProposedSegment:
        if self.clarification_required and not self.clarification_question:
            raise ValueError("A clarification_question must be provided when clarification_required is True.")
        return self
