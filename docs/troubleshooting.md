# Troubleshooting & Operations Runbook
## Fan360 Diagnostic Procedures & Support Guidelines

> **Educational Context**: This runbook provides diagnostic workflows for common runtime defects, provider exceptions, and data quality scenarios in Fan360.
> 
> *Classification Note*: Scenarios marked **[Exercised]** were actively reproduced and tested during automated test suite execution. Scenarios marked **[Runbook Only]** represent standard defensive operational guidance.

---

## 1. AI Audience Interpreter Issues

### 1.1 Missing or Unconfigured Credentials (`ConfigurationError`) [Exercised]
- **Symptom**: 
  - CLI: `[BLOCKED] Live verification could not proceed: Live LLM mode requested (LLM_MODE=live), but LLM_API_KEY environment variable is not configured.`
  - API: HTTP `503 Service Unavailable` with detail `"LLM Configuration Error: ..."`.
- **Diagnostic Steps**:
  ```bash
  python -c 'import os; print("LLM_MODE:", os.getenv("LLM_MODE"), "| KEY SET:", bool(os.getenv("LLM_API_KEY")))'
  ```
- **Likely Causes**:
  - `LLM_MODE=live` was exported, but `LLM_API_KEY` was not exported or is empty string.
  - Typo in environment variable name (`API_KEY` instead of `LLM_API_KEY`).
- **Recovery**:
  - For live execution: `export LLM_API_KEY="your_actual_key"`
  - For offline mock execution: `export LLM_MODE="mock"`
- **Verification**: Run `python -c "from src.ai.provider import get_llm_adapter; get_llm_adapter()"`.
- **Sanitized Info to Collect**: Model name (`LLM_MODEL`), provider base URL (`LLM_BASE_URL`), and exit code. **Never print or log the key value.**

---

### 1.2 Invalid API Key / HTTP 401 (`AuthenticationError`) [Exercised]
- **Symptom**: API returns HTTP `502 Bad Gateway` with `"Live LLM provider rejected API key (HTTP 401 Unauthorized)"`.
- **Diagnostic Steps**:
  - Test connectivity with a minimal curl request omitting headers from logs:
    ```bash
    curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $LLM_API_KEY" https://api.groq.com/openai/v1/models
    ```
- **Likely Causes**:
  - Revoked, expired, or mistyped API key.
  - Trailing newline or whitespace in the key string.
- **Recovery**:
  - Regenerate key in provider console (e.g., [console.groq.com](https://console.groq.com)).
  - Re-export with `strip()`: `export LLM_API_KEY="$(echo -n 'gsk_...' | xargs)"`.
- **Verification**: Run `python scripts/eval_ai_audience.py --live`.

---

### 1.3 Provider Rate Limit / HTTP 429 (`RateLimitError`) [Exercised]
- **Symptom**: API returns HTTP `502 Bad Gateway` with `"Live LLM provider rate limit / quota exceeded (HTTP 429)"`.
- **Diagnostic Steps**:
  - Inspect response header retry indicators (`retry-after` header).
  - Check provider console dashboard for Output Tokens Per Minute (OTPM) or Requests Per Minute (RPM).
- **Likely Causes**:
  - Small model tiers (e.g. `qwen/qwen3.8-27b`) on free tier often have low output token limits (e.g. 1,000 OTPM).
  - Rapid parallel execution of multiple queries.
- **Recovery**:
  - Switch to a model with higher capacity limits (e.g. `openai/gpt-oss-120b`).
  - Introduce brief sleep intervals between batch requests in script.
- **Verification**: Re-run evaluation suite; verify latency and HTTP 200 responses.

---

### 1.4 Provider Timeout / Network Unreachable (`ProviderTimeoutError`) [Exercised]
- **Symptom**: Request hangs for 10 seconds and raises `ProviderTimeoutError: Live LLM request timed out after 10.0s`.
- **Diagnostic Steps**:
  - Check general internet connectivity: `ping -c 3 api.groq.com`.
  - Check DNS resolution: `nslookup api.groq.com`.
- **Likely Causes**:
  - Egress firewall blocking outbound port 443.
  - Transient provider degradation.
- **Recovery**:
  - Check provider status page.
  - Increase timeout temporarily if network is high-latency: `LiveLLMProvider(..., timeout_seconds=20.0)`.
  - Fall back explicitly to mock mode: `export LLM_MODE=mock`.

---

### 1.5 Model Output Violates Pydantic Schema (`ProviderPayloadError`) [Exercised]
- **Symptom**: API returns HTTP `502 Bad Gateway` with `"Model output violates strict application schema"`.
- **Diagnostic Steps**:
  - Inspect application server logs for specific Pydantic validation error (e.g., `Value error, Operator 'gte' is unsupported`).
- **Likely Causes**:
  - Small or unaligned model hallucinated an unsupported operator (`LIKE`, `gte`) or unlisted field (`credit_score`).
  - Model response truncated by output token limits (`finish_reason="length"`).
- **Recovery**:
  - Ensure system prompt contains the explicit JSON schema with allowlisted fields.
  - Pre-validate and normalize common mathematical aliases (e.g. `gte` -> `>=`).
- **Verification**: Run unit tests: `pytest tests/test_ai_audience.py -k test_live_provider_violates_pydantic_schema_error`.

---

## 2. Data Pipeline & Database Operational Issues

### 2.1 PostgreSQL Connection Refused [Runbook Only]
- **Symptom**: `psycopg2.OperationalError: could not connect to server: Connection refused`.
- **Diagnostic Steps**:
  ```bash
  pg_isready -h localhost -p 5432
  psql -h localhost -U postgres -d fan360 -c "SELECT 1;"
  ```
- **Likely Causes**:
  - Local PostgreSQL daemon is stopped or not running on port 5432.
- **Recovery**:
  ```bash
  brew services start postgresql@16
  ```

---

### 2.2 Unexpected Low Consent-Eligible Count [Exercised]
- **Symptom**: User observes `1076/1803 eligible` for repeat purchasers, asking why 727 matching fans are excluded from marketing preview.
- **Diagnostic Steps**:
  - Query database directly to inspect consent distribution of matching fans:
    ```sql
    SELECT marketing_consent_status, COUNT(*)
    FROM fan_profiles
    WHERE valid_completed_order_count >= 2
    GROUP BY marketing_consent_status;
    ```
- **Findings**:
  - The 727 excluded fans have `marketing_consent_status` of `OPT_OUT` or `NONE`.
  - **This is expected and correct behavior**: The system mathematically enforces consent segregation. Qualifying on behavior does not grant permission to contact.

---

### 2.3 Empty Audience Preview Result (`0 matches`) [Exercised]
- **Symptom**: Preview returns `0 matches` for a seemingly common query (e.g. "Fans in Spain").
- **Diagnostic Steps**:
  - Check the generated SQL query and parameter tuple in application logs.
  - Verify country code formatting: ISO-3 code for Spain is `ESP`, not `SPA`.
- **Likely Causes**:
  - Mismatched categorical values (e.g. full country names vs ISO-3 alpha codes).
  - Overly restrictive conjunctive filters (e.g. spend > $10,000 AND order count = 0).
- **Recovery**:
  - Use editable review controls in the dashboard to relax thresholds or check supported ISO codes.
