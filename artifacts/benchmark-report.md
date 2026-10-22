# Fan360 Benchmark & Performance Report

**Generated**: 2026-10-22T17:55:48Z  
**Git Commit**: `56fddcf32ba695cfeff20a87fa408b6366580309`  
**Hardware & Runtime**: Darwin arm64 (10 CPU cores) | Python 3.14.6 | Apache Spark 4.2.0

## 1. Workload Specification
- **Synthetic Dataset**: `demo_10k` (Seed `42`)
- **Total Input Rows**: 110,624 rows across 5 tables
- **Total Valid Fan Profiles**: 10,000
- **Reference As-Of Timestamp**: `2026-10-01T00:00:00Z`

## 2. Pipeline Execution Benchmarks
Measured over 3 consecutive repetitions on identical input data:

| Metric | Measured Value | Notes |
| :--- | :--- | :--- |
| **Median Execution Time** | **4.724 s** | PySpark local transformation & aggregation |
| **Minimum Time** | **4.622 s** | Warm JVM run |
| **Maximum Time** | **4.799 s** | Cold JVM run |
| **Throughput** | **23,417 rows/s** | End-to-end transformation throughput |

### Baseline Comparison
- **In-Memory Python Baseline**: `0.106 s`
- **PySpark Local Engine**: `4.724 s`
- **Honest Engineering Analysis**: On small datasets (110,624 rows), a single-threaded in-memory Python script is faster than PySpark due to PySpark's JVM bridge (py4j), Catalyst query optimization overhead, and shuffle partition synchronization. PySpark was chosen for production scalability to gigabyte/terabyte workloads that exceed single-machine memory, not for single-node sub-second microbenchmarks.

## 3. FastAPI Latency Benchmarks
Measured across 100 requests per endpoint with 10 warm-up requests:

| Endpoint | p50 Latency | p95 Latency | p99 Latency | Error Rate |
| :--- | :--- | :--- | :--- | :--- |
| `GET /health` | 8.41 ms | 15.4 ms | 18.1 ms | 0.0% |
| `GET /segments` | 11.83 ms | 15.23 ms | 17.34 ms | 0.0% |
| `GET /fans/{fan_id}` | 8.89 ms | 14.5 ms | 15.41 ms | 0.0% |
| `GET /segments/.../members` | 10.69 ms | 20.42 ms | 25.5 ms | 0.0% |
