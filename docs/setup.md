# Setup, Configuration & Teardown Runbook
## Fan360 Reproducible Environment Guide

> **Scope**: This runbook provides exact, step-by-step instructions to initialize, execute, evaluate, and tear down the Fan360 environment locally on macOS/Linux.

---

## 1. Prerequisites & Version Requirements

| Dependency | Minimum Version | Verified Local Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Python** | `>= 3.10` | `3.14.6` (arm64) | Application runtime, FastAPI, PySpark, Pydantic |
| **Java (JDK)** | OpenJDK 11 or 17 | OpenJDK 21 (Temurin) | Local PySpark engine execution |
| **PostgreSQL** | `>= 14` | `PostgreSQL 16.1` (Homebrew) | Target database storage & SQL evaluation |
| **Git** | `>= 2.30` | `2.43.0` | Version control & branch management |

---

## 2. Step-by-Step Installation

### Step 2.1: Clone & Virtual Environment Setup
```bash
# 1. Clone repository
git clone https://github.com/tejashr0716/fan360.git
cd fan360

# 2. Checkout feature branch
git checkout feature/llm-audience-builder

# 3. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 4. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 2.2: Disposable Database Setup
```bash
# 1. Ensure PostgreSQL is running
brew services start postgresql@16

# 2. Create fresh disposable database
createdb fan360 || echo "Database fan360 already exists"

# 3. Initialize schema tables
.venv/bin/python -c '
from src.pipeline.db_loader import DatabaseLoader
loader = DatabaseLoader()
loader.init_tables()
print("PostgreSQL tables successfully initialized.")
'
```

---

### Step 2.3: Environment Configuration (.env)
Copy the safe template:
```bash
cp .env.example .env
```
Default `.env` configuration (Mock Mode):
```ini
FAN360_DB_HOST=localhost
FAN360_DB_PORT=5432
FAN360_DB_NAME=fan360
FAN360_DB_USER=postgres
FAN360_DB_PASSWORD=

# Mode options: 'mock' (default) or 'live'
LLM_MODE=mock
```

To enable Live LLM execution via Groq (Free Tier):
```ini
LLM_MODE=live
LLM_API_KEY=your_actual_groq_api_key_here
LLM_MODEL=openai/gpt-oss-120b
LLM_BASE_URL=https://api.groq.com/openai/v1
```

---

## 3. Data Generation & Pipeline Execution

### Step 3.1: Generate Deterministic Synthetic Data (10,000 Fans)
```bash
.venv/bin/python scripts/generate_data.py --fans 10000 --seed 42
```
*Output files generated in `data/raw/`: `fans.csv`, `orders.csv`, `web_events.csv`, `email_events.csv`, `consent.csv`.*

### Step 3.2: Execute Data Quality & PySpark Batch Pipeline
```bash
.venv/bin/python scripts/run_pipeline.py
```
*Executes validation, quarantines defective records, aggregates Fan 360 metrics in PySpark, and loads PostgreSQL tables.*

---

## 4. Verification & Testing

### Step 4.1: Run Full Pytest Suite (42 Tests)
```bash
.venv/bin/pytest -v
```
*Expected: 42 passed in ~26 seconds.*

### Step 4.2: Run AI Audience Interpreter Evaluation Suite

#### Deterministic Mock Evaluation:
```bash
.venv/bin/python scripts/eval_ai_audience.py --output artifacts/eval-report.md
```

#### Live Provider Evaluation (Requires API Key):
```bash
export LLM_API_KEY="your_api_key"
export LLM_BASE_URL="https://api.groq.com/openai/v1"
export LLM_MODEL="openai/gpt-oss-120b"

.venv/bin/python scripts/eval_ai_audience.py --live --output artifacts/live-eval-report.md
```

---

## 5. Starting Application Services

### Step 5.1: Start FastAPI Backend (Port 8000)
```bash
.venv/bin/uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```
- Swagger OpenAPI Docs: `http://localhost:8000/docs`
- Healthcheck: `curl http://localhost:8000/health`

### Step 5.2: Start Streamlit Dashboard (Port 8501)
```bash
.venv/bin/streamlit run src/ui/dashboard.py
```
- Interactive UI: `http://localhost:8501`
- Navigate to **"AI Audience Builder"** tab to test conversational audience queries.

---

## 6. Teardown & Clean-up

To reset the local environment cleanly without leaving background services running:

```bash
# 1. Stop background python processes
pkill -f "uvicorn src.api.app" || true
pkill -f "streamlit run src/ui/dashboard" || true

# 2. Reset / Drop disposable database
dropdb fan360 --if-exists

# 3. Remove synthetic data artifacts (Optional)
rm -rf data/raw/*.csv
rm -rf data/processed/*.csv
rm -rf spark-warehouse/ metastore_db/ derby.log

# 4. Deactivate virtual environment
deactivate
```
