"""
Fan360 LLM Provider Adapter
Provides structured natural language requirement interpretation.
Implements explicit provider modes (live vs mock), no silent fallback,
bounded retries, strict JSON-schema enforcement, and zero customer data transfer.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple, Union

from pydantic import ValidationError

from src.ai.schema import ALLOWLISTED_FIELDS, ProposedSegment, SegmentFilter

logger = logging.getLogger(__name__)


# Custom Domain Exceptions
class LLMError(Exception):
    """Base exception for LLM operations."""
    pass


class ConfigurationError(LLMError):
    """Raised when provider configuration or credentials are missing/invalid."""
    pass


class AuthenticationError(LLMError):
    """Raised when provider rejects API key (HTTP 401)."""
    pass


class RateLimitError(LLMError):
    """Raised when provider rate limit / quota is exceeded (HTTP 429)."""
    pass


class ProviderRefusalError(LLMError):
    """Raised when model refuses request or triggers content safety filters."""
    pass


class ProviderTimeoutError(LLMError):
    """Raised when provider request exceeds allowable latency threshold."""
    pass


class ProviderPayloadError(LLMError):
    """Raised when provider output cannot be parsed as valid structured JSON."""
    pass


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
5. If the user requests attributes outside the allowlisted fields (e.g. credit score, age, tire pressure), set "clarification_required": true and explain that the field is unsupported.
6. You MUST return ONLY valid JSON matching the exact schema:
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

    def interpret_request(
        self,
        user_query: str,
    ) -> Tuple[ProposedSegment, str, Dict[str, Any]]:
        raise NotImplementedError


class MockLLMProvider(BaseLLMAdapter):
    """
    Deterministic mock provider for reliable local demonstration and automated testing.
    Labeled explicitly as 'Mock LLM — not a live model'.
    """

    def interpret_request(
        self,
        user_query: str,
    ) -> Tuple[ProposedSegment, str, Dict[str, Any]]:
        t0 = time.perf_counter()
        q = user_query.strip().lower()

        # Check for empty or oversized input
        if not q:
            raise ValueError("Audience requirement cannot be empty.")
        if len(user_query) > 1000:
            raise ValueError("Audience requirement exceeds maximum allowed length of 1,000 characters.")

        mode_label = "Mock LLM — not a live model"

        # Check for unsupported fields (e.g. credit score, age, phone)
        unsupported_keywords = ["credit score", "age", "phone", "gender", "address", "net worth", "salary"]
        for unk in unsupported_keywords:
            if unk in q:
                proposal = ProposedSegment(
                    name="Unsupported Field Requested",
                    description=f"Attribute '{unk}' is outside allowlisted profile fields.",
                    filters=[],
                    explanation=f"Fan360 profile schema does not track '{unk}'. Only orders, spend, country, language, driver, and activity are supported.",
                    clarification_required=True,
                    clarification_question=f"The field '{unk}' is unsupported. Would you like to filter on country, preferred driver, order count, or spend instead?",
                )
                dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                return proposal, mode_label, {"latency_ms": dt_ms, "mocked": True}

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
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return proposal, mode_label, {"latency_ms": dt_ms, "mocked": True}

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
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return proposal, mode_label, {"latency_ms": dt_ms, "mocked": True}

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
                description=f"Fans with {min_orders} or more completed orders.",
                filters=filters,
                explanation=exp,
                clarification_required=False,
                clarification_question=None,
            )
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return proposal, mode_label, {"latency_ms": dt_ms, "mocked": True}

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
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return proposal, mode_label, {"latency_ms": dt_ms, "mocked": True}

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
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return proposal, mode_label, {"latency_ms": dt_ms, "mocked": True}

        # Pattern 4: Driver preference (e.g. Lucas Rossi)
        if "lucas rossi" in q:
            filters = [SegmentFilter(field="preferred_driver", operator="==", value="Lucas Rossi")]
            exp = "Filtered on preferred_driver == 'Lucas Rossi'."
            if re.search(r"\b(brazil|bra)\b", q):
                filters.append(SegmentFilter(field="country", operator="==", value="BRA"))
                exp += " Added filter country == 'BRA'."

            proposal = ProposedSegment(
                name="Lucas Rossi Supporters",
                description="Fans whose preferred driver is Lucas Rossi.",
                filters=filters,
                explanation=exp,
                clarification_required=False,
                clarification_question=None,
            )
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return proposal, mode_label, {"latency_ms": dt_ms, "mocked": True}

        # Pattern 5: Simple country filter
        country_matches = [
            ("USA", r"\b(usa?|united states)\b"),
            ("GBR", r"\b(gbr|uk|great britain|united kingdom)\b"),
            ("FRA", r"\b(france|fra)\b"),
            ("BRA", r"\b(brazil|bra)\b"),
            ("DEU", r"\b(germany|deu)\b"),
        ]
        for iso_c, c_regex in country_matches:
            if re.search(c_regex, q):
                proposal = ProposedSegment(
                    name=f"{iso_c} Fans",
                    description=f"Fans located in {iso_c}.",
                    filters=[SegmentFilter(field="country", operator="==", value=iso_c)],
                    explanation=f"Mapped geographic requirement to country == '{iso_c}'.",
                    clarification_required=False,
                    clarification_question=None,
                )
                dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                return proposal, mode_label, {"latency_ms": dt_ms, "mocked": True}

        # Default ambiguous request
        proposal = ProposedSegment(
            name="Unclear Audience Request",
            description="Requirement could not be deterministically mapped to allowlisted fields.",
            filters=[],
            explanation="Could not find clear matching attributes among allowlisted fields.",
            clarification_required=True,
            clarification_question="Could you specify the target country, driver, minimum spend, or purchase count you would like to filter on?",
        )
        dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return proposal, mode_label, {"latency_ms": dt_ms, "mocked": True}


class LiveLLMProvider(BaseLLMAdapter):
    """
    Live LLM provider adapter using standard OpenAI-compatible REST API endpoints.
    Configured strictly through server-side environment variables.
    Never sends customer records, database contents, or connection strings.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 1,
        http_client: Optional[Any] = None,
    ):
        if not api_key or not api_key.strip():
            raise ConfigurationError("LiveLLMProvider requires a non-empty API key.")

        self.api_key = api_key.strip()
        self.model_name = model_name or "gpt-4o-mini"
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._http_client = http_client

    def _execute_http_post(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Executes HTTP POST request with bounded transient retries."""
        data_bytes = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/chat/completions"

        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Fan360-AudienceBuilder/1.0",
            },
        )

        attempts = 0
        last_exception = None

        while attempts <= self.max_retries:
            attempts += 1
            t0 = time.perf_counter()
            try:
                opener = self._http_client or urllib.request.urlopen
                with opener(req, timeout=self.timeout_seconds) as resp:
                    resp_bytes = resp.read()
                    dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    parsed_body = json.loads(resp_bytes.decode("utf-8"))

                    # Extract metadata
                    headers_dict = dict(resp.headers) if hasattr(resp, "headers") else {}
                    request_id = headers_dict.get("x-request-id") or parsed_body.get("id", "req_unknown")
                    usage = parsed_body.get("usage", {})

                    metadata = {
                        "request_id": request_id,
                        "latency_ms": dt_ms,
                        "model": parsed_body.get("model", self.model_name),
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                        "mocked": False,
                    }
                    return parsed_body, metadata

            except urllib.error.HTTPError as exc:
                status_code = exc.code
                err_text = ""
                try:
                    err_text = exc.read().decode("utf-8")
                except Exception:
                    pass

                # Fail fast on non-transient client errors
                if status_code == 401:
                    raise AuthenticationError(
                        "Live LLM provider rejected API key (HTTP 401 Unauthorized). "
                        "Check your LLM_API_KEY environment variable."
                    ) from exc
                elif status_code == 429:
                    raise RateLimitError(
                        f"Live LLM provider rate limit / quota exceeded (HTTP 429): {err_text[:200]}"
                    ) from exc
                elif status_code == 400:
                    raise ProviderPayloadError(
                        f"Live LLM provider rejected request payload (HTTP 400): {err_text[:200]}"
                    ) from exc
                elif status_code in (500, 502, 503, 504) and attempts <= self.max_retries:
                    logger.warning("Transient HTTP %d from provider. Retrying attempt %d...", status_code, attempts)
                    time.sleep(0.5)
                    last_exception = exc
                    continue
                else:
                    raise LLMError(f"Live LLM provider returned HTTP {status_code}: {err_text[:200]}") from exc

            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempts <= self.max_retries:
                    logger.warning("Transient network error '%s'. Retrying attempt %d...", str(exc), attempts)
                    time.sleep(0.5)
                    last_exception = exc
                    continue
                raise ProviderTimeoutError(
                    f"Live LLM request timed out after {self.timeout_seconds}s or failed connection: {str(exc)}"
                ) from exc

        if last_exception:
            raise LLMError(f"Provider request failed after {attempts} attempts: {str(last_exception)}")
        raise LLMError("Unknown provider failure.")

    def interpret_request(
        self,
        user_query: str,
    ) -> Tuple[ProposedSegment, str, Dict[str, Any]]:
        """
        Submits natural-language requirement to live provider.
        Enforces strict Pydantic validation on returned content.
        Does NOT silently fall back to mock on failure.
        """
        if not user_query or not user_query.strip():
            raise ValueError("Audience requirement cannot be empty.")
        if len(user_query) > 1000:
            raise ValueError("Audience requirement exceeds maximum allowed length of 1,000 characters.")

        # Construct JSON schema for strict structured output
        pydantic_schema = ProposedSegment.model_json_schema()

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Audience requirement: {user_query.strip()}"},
            ],
            "temperature": 0.0,
            "max_tokens": 800,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "proposed_segment",
                    "strict": True,
                    "schema": pydantic_schema,
                },
            },
        }

        # Fallback to json_object if testing on a provider that does not support json_schema
        try:
            raw_resp, metadata = self._execute_http_post(payload)
        except ProviderPayloadError:
            # Retry with standard json_object
            payload["response_format"] = {"type": "json_object"}
            raw_resp, metadata = self._execute_http_post(payload)

        # Parse message content
        choices = raw_resp.get("choices", [])
        if not choices:
            raise ProviderPayloadError("Provider response contained empty 'choices' list.")

        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise ProviderPayloadError("Model response was truncated due to output token limits.")
        if finish_reason == "content_filter":
            raise ProviderRefusalError("Model refused request due to content safety filtering.")

        message = choice.get("message", {})
        refusal = message.get("refusal")
        if refusal:
            raise ProviderRefusalError(f"Model refused request: {refusal}")

        content_str = message.get("content", "")
        if not content_str:
            raise ProviderPayloadError("Model returned empty content payload.")

        try:
            parsed_dict = json.loads(content_str)
        except json.JSONDecodeError as exc:
            raise ProviderPayloadError(f"Model output is not valid JSON: {str(exc)}") from exc

        try:
            proposal = ProposedSegment(**parsed_dict)
        except ValidationError as exc:
            raise ProviderPayloadError(f"Model output violates strict application schema: {str(exc)}") from exc

        mode_str = f"Live Model ({self.model_name})"
        return proposal, mode_str, metadata


def get_llm_adapter(mode: Optional[str] = None) -> BaseLLMAdapter:
    """
    Factory creating requested provider adapter.
    Enforces explicit mode checking without silent fallbacks.
    Modes:
      - 'mock': deterministic local mock adapter
      - 'live': configured live LLM provider
    """
    effective_mode = (mode or os.getenv("LLM_MODE", "mock")).strip().lower()

    if effective_mode == "mock":
        return MockLLMProvider()

    if effective_mode == "live":
        api_key = os.getenv("LLM_API_KEY")
        if not api_key or not api_key.strip():
            raise ConfigurationError(
                "Live LLM mode requested (LLM_MODE=live), but LLM_API_KEY environment variable is not configured. "
                "Configure a valid LLM_API_KEY or set LLM_MODE=mock."
            )
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        base_url = os.getenv("LLM_BASE_URL")
        return LiveLLMProvider(api_key=api_key, model_name=model, base_url=base_url)

    raise ConfigurationError(
        f"Unsupported LLM_MODE '{effective_mode}'. Supported modes are: 'mock', 'live'."
    )
