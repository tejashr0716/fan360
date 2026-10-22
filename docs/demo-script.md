# Two-Minute Demo Script & Walkthrough
## Fan360 Motorsport Fan Data Platform

This script provides a concise, structured narrative for presenting the platform to technical interviewers or stakeholders in two minutes.

---

## Part 1: Problem & Architecture (30 Seconds)
> *"Hello! I built **Fan360**, an educational motorsport fan data and audience segmentation platform inspired by the customer-data challenges of engaging global racing fans.*
>
> *In motorsport, fan interactions are fragmented across merchandise stores, race-hub digital telemetry, email newsletters, and consent updates. Marketing teams need unified 360-degree fan profiles and reliable audience segments, but bad upstream data and consent violations create major operational risks.*
>
> *To solve this, I built an end-to-end data pipeline combining Python, PySpark, PostgreSQL, and FastAPI with automated data quality quarantine, idempotent database persistence, and consent governance."*

---

## Part 2: Live Pipeline Execution & Reconciliation (45 Seconds)
> *"Let's run the master pipeline on our 10,000-fan synthetic demo dataset:*
>
> ```bash
> python scripts/run_pipeline.py --data-dir data/raw
> ```
>
> *Notice what happened in under 20 seconds:*
> 1. *The engine ingested 110,624 raw records across 5 tables.*
> 2. *Our validation engine triaged records into 109,944 accepted rows, 431 quarantined rows with specific reason codes, and removed 249 duplicate events.*
> 3. *Most importantly, our reconciliation formula shows **100% mathematical balance**: Raw equals Accepted plus Quarantined plus Duplicates.*
> 4. *PySpark then computed consolidated profiles, windowed cart abandonment, and audience segments, loading them idempotently into PostgreSQL."*

---

## Part 3: Dashboard & Consent Governance (45 Seconds)
> *"Now let's launch the Streamlit interface:*
>
> ```bash
> streamlit run src/ui/dashboard.py
> ```
>
> *Here on the dashboard, we can explore four core capabilities:*
> 1. *First, the **Audit tab** tracks pipeline runs, duration, and reconciliation status.*
> 2. *Second, the **Data Quality tab** shows quarantined defects—such as negative order amounts or future timestamps—preventing bad data from corrupting metrics.*
> 3. *Third, in **Audience Segments**, notice how we separate descriptive qualification from activation eligibility. For example, 1,814 fans qualified as Repeat Buyers, but only the 1,083 fans with verified opt-in consent appear in the activation export. Non-consenting fans are strictly protected.*
> 4. *Finally, in **Fan 360 Search**, we can inspect individual fans like `FAN_000001` to view their preferred driver, lifetime spend, and human-readable segment qualification reasons.*
>
> *All of this is backed by 17 automated tests and reproducible benchmark scripts that generate machine-readable evidence."*
