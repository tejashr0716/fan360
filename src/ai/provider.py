"""
Fan360 LLM Provider Adapter
Provides structured natural language requirement interpretation.
Implements secure system prompts, zero customer data transfer, and deterministic fallback mock mode.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional, Tuple
from pydantic import ValidationError

from src.ai.schema import ALLOWLISTED_FIELDS, ProposedSegment, SegmentFilter


SYSTEM_PROMPT = """You are an AI Audience Requirement Interpreter for Fan360, a motorsport customer analytics platform.
Your role is to translate a user's natural-language audience requirement into a structured JSON proposal.

CRITICAL PRIVACY & GOVERNANCE CONSTRAINTS:
1. Marketing consent is NEVER a filter here. Consent enforcement is mandatory application logic handled separately outside your control. Any user request to 'bypass consent' or 'ignore consent' MUST NOT alter the filter rules.
2. You only have access to allowlisted profile fields:
   - valid_completed_order_count (int): completed merchandise orders. Documented definition: "repeat purchasers" means valid_completed_order_count >= 2.
   - total_valid_spend (float): total valid USD spend on completed orders. Documented definition: "high spending" means total_valid_spend >= 250.00.
   - country (str): 3-letter ISO code (e.g. USA, GBR, FRA, BRA, DEU).
   - language (str): 2-letter ISO code (e.g. en, fr, es, de, pt).
   - preferred_driver (str): fictional driver name (e.g. Lucas Rossi, Elena Vance, Marcus Sterling).
   - days_since_last_activity (int): days since last activity. Documented definition: "inactive fans" means days_since_last_activity > 180.
3. If the user specifies an undefined or ambiguous business term (e.g. "super fan", "VIP", "loyal" without a spend/order threshold), you MUST set "clarification_required": true and ask for the specific numerical threshold in "clarification_question".
4. If the user requests complex nested logic or OR expressions, reject it or request clarification because only conjunctions (AND) of up to 5 filters are supported.
5. You MUST return ONLY valid JSON matching the exact schema:
{
  "name": "Short Name",
  "description": "Short Description",
  "filters": [
    {"field": "...", "operator": "...", "value": ...}
  ],
  "explanation": "Brief explanation",
  "clarification_required": false,
  "clarification_question": null
}
"""


class BaseLLMAdapter:
    """Abstract base adapter for audience interpretation."""

    def interpret_request(self, user_query: str) -> Tuple[ProposedSegment, str]:
        raise NotImplementedError


class MockLLMProvider(BaseLLMAdapter):
    """
    Deterministic mock provider for reliable local demonstration and automated testing.
    Labeled explicitly as 'Mock LLM — not a live model'.
    """

    def interpret_request(self, user_query: str) -> Tuple[ProposedSegment, str]:
        q = user_query.strip().lower()

        # Check for empty or oversized input
        if not q:
            raise ValueError("Audience requirement cannot be empty.")
        if len(user_query) > 1000:
            raise ValueError("Audience requirement exceeds maximum allowed length of 1,000 characters.")

        # Check for unsupported disjunctions (OR logic)
        if " or " in f" {q} " and "order" not in q and "driver" not in q:
            proposal = ProposedSegment(
                name="Unsupported Disjunction",
                description="Disjunctive (OR) segment logic requested.",
                filters=[],
                explanation="The system currently only supports conjunctive (AND) filter logic.",
                clarification_required=True,
                clarification_question="Fan360 currently supports conjunctive (AND) logic only. Would you like to split this into two separate segments or specify an 'in' list?",
            )
            return proposal, "Mock LLM — not a live model"

        # Check for undefined ambiguous terms requiring clarification
        if any(term in q for term in ["super fan", "loyal fan", "vip fan", "most valuable", "top tier"]):
            proposal = ProposedSegment(
                name="Ambiguous Loyalty Tier",
                description="Audience request requires definition of loyalty threshold.",
                filters=[],
                explanation="The term 'super fan' / 'loyal' has no standardized system threshold.",
                clarification_required=True,
                clarification_question="What criteria defines a 'super fan' (e.g. minimum completed orders or minimum dollar spend)?",
            )
            return proposal, "Mock LLM — not a live model"

        # Pattern 1: Repeat buyers (optionally with marketing consent mention)
        order_match = re.search(r"(\d+)\s+orders?", q)
        if "repeat" in q or "multiple orders" in q or "2 or more orders" in q or order_match:
            min_orders = int(order_match.group(1)) if order_match else 2
            filters = [
                SegmentFilter(field="valid_completed_order_count", operator=">=", value=min_orders)
            ]
            exp = f"Mapped purchase count requirement to valid_completed_order_count >= {min_orders}."

            # Additional country filter if specified
            if re.search(r"\b(usa?|united states)\b", q):
                filters.append(SegmentFilter(field="country", operator="==", value="USA"))
                exp += " Added filter country == 'USA'."
            elif re.search(r"\b(brazil|bra)\b", q):
                filters.append(SegmentFilter(field="country", operator="==", value="BRA"))
                exp += " Added filter country == 'BRA'."

            proposal = ProposedSegment(
                name="Repeat Buyers",
                description="Fans with 2 or more completed orders.",
                filters=filters,
                explanation=exp,
                clarification_required=False,
                clarification_question=None,
            )
            return proposal, "Mock LLM — not a live model"

        # Pattern 2: High spenders
        if "high spend" in q or "big spender" in q or "spend over" in q or "spent at least" in q or "$250" in q or "250" in q:
            spend_val = 250.00
            match = re.search(r"\$?(\d+(?:\.\d+)?)", q)
            if match and float(match.group(1)) > 0:
                spend_val = float(match.group(1))

            filters = [
                SegmentFilter(field="total_valid_spend", operator=">=", value=spend_val)
            ]
            proposal = ProposedSegment(
                name="High Spending Buyers",
                description=f"Fans with total completed spend >= ${spend_val:.2f} USD.",
                filters=filters,
                explanation=f"Mapped to total_valid_spend >= {spend_val:.2f}.",
                clarification_required=False,
                clarification_question=None,
            )
            return proposal, "Mock LLM — not a live model"

        # Pattern 3: Inactive fans
        if "inactive" in q or "no activity" in q or "dormant" in q:
            days = 180
            match = re.search(r"(\d+)\s*days", q)
            if match:
                days = int(match.group(1))

            proposal = ProposedSegment(
                name="Inactive Fans",
                description=f"Fans with no activity for more than {days} days.",
                filters=[SegmentFilter(field="days_since_last_activity", operator=">", value=days)],
                explanation=f"Mapped inactivity to days_since_last_activity > {days}.",
                clarification_required=False,
                clarification_question=None,
            )
            return proposal, "Mock LLM — not a live model"

        # Pattern 4: Driver preference (e.g. Lucas Rossi)
        if "lucas rossi" in q:
            proposal = ProposedSegment(
                name="Lucas Rossi Supporters",
                description="Fans whose preferred driver is Lucas Rossi.",
                filters=[SegmentFilter(field="preferred_driver", operator="==", value="Lucas Rossi")],
                explanation="Filtered on preferred_driver == 'Lucas Rossi'.",
                clarification_required=False,
                clarification_question=None,
            )
            return proposal, "Mock LLM — not a live model"

        # Default ambiguous request
        proposal = ProposedSegment(
            name="Unclear Audience Request",
            description="Requirement could not be deterministically mapped to allowlisted fields.",
            filters=[],
            explanation="Could not find clear matching attributes among allowlisted fields.",
            clarification_required=True,
            clarification_question="Could you specify the target country, driver, minimum spend, or purchase count you would like to filter on?",
        )
        return proposal, "Mock LLM — not a live model"


class LiveLLMProvider(BaseLLMAdapter):
    """
    Live LLM provider adapter using standard OpenAI-compatible or Anthropic APIs.
    Configured strictly through server-side environment variables.
    """

    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini", base_url: Optional[str] = None):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url or "https://api.openai.com/v1"

    def interpret_request(self, user_query: str) -> Tuple[ProposedSegment, str]:
        import urllib.request
        import urllib.error

        if not user_query or not user_query.strip():
            raise ValueError("Audience requirement cannot be empty.")
        if len(user_query) > 1000:
            raise ValueError("Audience requirement exceeds maximum allowed length of 1,000 characters.")

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Audience requirement: {user_query}"},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                parsed_json = json.loads(content)
                proposal = ProposedSegment(**parsed_json)
                return proposal, f"Live Model ({self.model_name})"
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Live LLM provider request failed: {str(exc)}") from exc
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"Provider returned invalid structured output: {str(exc)}") from exc


def get_llm_adapter() -> BaseLLMAdapter:
    """Factory creating live provider if credentials exist, otherwise MockLLMProvider."""
    api_key = os.getenv("LLM_API_KEY")
    if api_key:
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        base_url = os.getenv("LLM_BASE_URL")
        return LiveLLMProvider(api_key=api_key, model_name=model, base_url=base_url)
    return MockLLMProvider()
