# Technical Interview Preparation Guide
## Fan360 Architecture, Design Decisions & Honest Answers

This guide prepares you to answer technical and architectural questions about your implementation with honesty and depth.

---

## 1. Top 5 Concepts to Master Before Presenting

### Concept 1: Idempotency in Data Pipelines
- **What it means**: Running an operation multiple times with identical inputs produces the exact same outcome without duplicate rows, unintended mutations, or inflated metrics.
- **In Fan360**:
  - We use stable primary keys (`fan_id`, `(fan_id, segment_code)`).
  - PostgreSQL writes use `ON CONFLICT DO UPDATE`.
  - In `tests/test_idempotency.py`, we verify row counts and canonical SHA-256 hashes of the business outputs across consecutive runs.

### Concept 2: Hierarchical Data Validation & Non-Double-Counting
- **What it means**: In real pipelines, a bad record often suffers from multiple defects (e.g. an order missing a fan ID with a negative amount).
- **In Fan360**:
  - If you count defects independently across tables, your quarantine totals exceed raw input counts.
  - We enforced an explicit evaluation hierarchy: Structural (`MISSING_REQUIRED_FIELD`) > Referential (`UNKNOWN_FAN_REFERENCE`) > Temporal (`INVALID_TIMESTAMP`) > Domain (`INVALID_ORDER_AMOUNT`) > Enum (`INVALID_CONSENT_STATUS`).
  - Each record receives one primary reason code, ensuring:
    $$\text{Raw} = \text{Accepted} + \text{Quarantined} + \text{Duplicates}$$

### Concept 3: Latest-Effective-Update Consent Resolution
- **What it means**: Consent permissions are event-driven time series. A customer may opt in, unsubscribe, re-subscribe, and submit updates across web forms and email links.
- **In Fan360**:
  - We evaluate consent up to a fixed `as_of` timestamp.
  - We apply a window function partitioned by `fan_id` ordered by `update_timestamp DESC, consent_id DESC`.
  - Missing consent defaults to `NONE` (never implies permission).
  - Marketing activations enforce a strict filter: only `OPT_IN` fans are exported.

### Concept 4: Window-Based Abandoned Cart Logic
- **What it means**: Naive implementations define abandoned cart as "any cart event without any purchase ever." In production, carts have a temporal window and must be matched with resolving purchases.
- **In Fan360**:
  - We filter `add_to_cart` events within a 14-day window relative to `as_of`.
  - We perform an anti-join against completed orders placed by that fan that reference that specific `cart_id` at or after the cart addition.
  - If a resolving order exists, the cart is considered completed and excluded from abandoned-cart recovery.

### Concept 5: PySpark Local Architecture vs In-Memory Python
- **What it means**: PySpark operates via a JVM bridge (`py4j`), converting DataFrame transformations into a Directed Acyclic Graph (DAG) executed across partitions.
- **In Fan360**:
  - On our 110k synthetic dataset, pure Python takes ~0.10s while PySpark takes ~4.6s due to JVM startup, Catalyst planning, and partition synchronization.
  - *Why use PySpark then?* Because when data scales from 100k rows to 100 million rows (gigabytes or terabytes), Python single-process memory crashes (OOM), whereas PySpark distributes memory and disk spill across worker nodes.

---

## 2. Challenging Technical Interview Questions & Honest Answers

### Q1: "Why did you build this with PySpark on a local laptop instead of just using pandas or DuckDB?"
> *"That's a deliberate architectural trade-off. For 10,000 fans and 100,000 events, a single-node engine like DuckDB or pure Python is undeniably faster—in our benchmarks, pure Python finished in 0.10 seconds versus PySpark's 4.6 seconds.  
> However, motorsport fan platforms in production process high-frequency streaming events, race telemetry, and millions of store interactions. I chose PySpark to demonstrate distributed window functions, Catalyst-optimized joins, and partition strategies so the transformation code is directly portable to Databricks, EMR, or a production Spark cluster without rewriting the business logic."*

### Q2: "How do you ensure you don't violate GDPR or privacy regulations if an opt-out occurs between pipeline runs?"
> *"In a batch architecture, there is inherently a window between runs. To handle this safely:  
> 1. We strictly separate descriptive segment qualification from activation exports. Descriptive profiles show engagement facts, but the activation export table strictly filters for `OPT_IN`.  
> 2. Before any campaign export or downstream sync is triggered, the system checks the latest consent table.  
> 3. In a real-time production setting, consent withdrawal events would publish to a real-time suppression topic (e.g. Kafka or Redis) to invalidate activations immediately between daily Spark batch runs."*

### Q3: "What happens if an order arrives for a fan that was created after the order timestamp?"
> *"Our `DataValidator` enforces referential integrity and temporal consistency. If an event has a timestamp beyond the configured `as_of_timestamp`, or if an event references an unknown `fan_id`, it is quarantined under `INVALID_TIMESTAMP` or `UNKNOWN_FAN_REFERENCE`. The record is logged with its raw payload so data engineers can investigate upstream synchronization delays."*

### Q4: "How did you test your audience segmentation logic to make sure the code wasn't just confirming its own bugs?"
> *"I avoided testing the pipeline against results generated by the pipeline itself. Instead, I hand-authored a small 'golden fixture' dataset with 10 fans containing edge cases: tie-breaking consent updates, resolving cart purchases, spend boundaries (\$249.99 vs \$250.00), and inactive fans.  
> I then wrote an independent `expected_memberships.json` file specifying which fans should qualify. Our automated tests assert a 100% exact match against those independently authored expectations."*
