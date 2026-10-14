"""
Empirical Benchmark Evaluation Protocol
Measures actual API response times, risk scoring latency (p50, p95, p99),
transaction throughput, and failure recovery.
"""

import time
import statistics
import json
from fastapi.testclient import TestClient
from app.main import app
from app.services.risk_scoring import score_factors
from app.services.simulator import TransactionGenerator
from app.auth.security import create_access_token

client = TestClient(app)

results = {}

# 1. Measure Risk Scoring Execution Latency (100 repetitions)
latencies_ms = []
mock_factors = {
    "shared_device": 2,
    "shared_location": 1,
    "multi_hop_path": 1,
    "cycle_participation": 1,
    "high_transaction_velocity": 6,
    "suspicious_connections": 2,
}

for i in range(100):
    t0 = time.perf_counter()
    res = score_factors(f"TXN_BENCH_{i:04d}", mock_factors)
    t1 = time.perf_counter()
    latencies_ms.append((t1 - t0) * 1000.0)

results["risk_scoring_latency_ms"] = {
    "repetitions": len(latencies_ms),
    "min": round(min(latencies_ms), 4),
    "max": round(max(latencies_ms), 4),
    "mean": round(statistics.mean(latencies_ms), 4),
    "p50": round(statistics.median(latencies_ms), 4),
    "p95": round(statistics.quantiles(latencies_ms, n=20)[18], 4),
    "p99": round(statistics.quantiles(latencies_ms, n=100)[98], 4),
}

# 2. Measure API Endpoint Response Times (5 repetitions each)
endpoints = [
    ("GET", "/health", None),
    ("POST", "/api/v1/auth/login", {"username": "admin", "password": "Admin@FraudGraph2026!"}),
    ("GET", "/api/v1/ml/info", None),
    ("GET", "/api/v1/cases", None),
    ("GET", "/api/v1/stream/status", None),
]

# Generate auth token for protected routes
token, _, _ = create_access_token("USR_ADMIN_001", "admin", "admin")
auth_headers = {"Authorization": f"Bearer {token}"}

api_metrics = {}
for method, path, payload in endpoints:
    path_latencies = []
    status_codes = []
    headers = auth_headers if path != "/api/v1/auth/login" and path != "/health" else {}
    for _ in range(5):
        t0 = time.perf_counter()
        if method == "GET":
            res = client.get(path, headers=headers)
        else:
            res = client.post(path, json=payload, headers=headers)
        t1 = time.perf_counter()
        path_latencies.append((t1 - t0) * 1000.0)
        status_codes.append(res.status_code)

    api_metrics[path] = {
        "method": method,
        "sample_size": 5,
        "status_code": status_codes[0],
        "all_200_or_201": all(c in (200, 201) for c in status_codes),
        "mean_ms": round(statistics.mean(path_latencies), 2),
        "p50_ms": round(statistics.median(path_latencies), 2),
        "p95_ms": round(max(path_latencies), 2),
        "min_ms": round(min(path_latencies), 2),
        "max_ms": round(max(path_latencies), 2),
    }

results["api_endpoints"] = api_metrics

# 3. Measure Transaction Generation & Scoring Processing Throughput
generator = TransactionGenerator(seed=42)
t_start = time.perf_counter()
tx_count = 1000
for _ in range(tx_count):
    tx = generator.generate()
    _ = score_factors(tx.transaction_id, mock_factors)
t_elapsed = time.perf_counter() - t_start

results["transaction_throughput"] = {
    "transactions_processed": tx_count,
    "elapsed_seconds": round(t_elapsed, 4),
    "throughput_tx_per_sec": round(tx_count / t_elapsed, 1),
}

# 4. Error Rates and Failure Recovery Behavior
failure_tests = {}

# Test A: Malformed Token
res_bad_token = client.get("/api/v1/cases", headers={"Authorization": "Bearer invalid.token.value"})
failure_tests["malformed_jwt"] = {
    "status_code": res_bad_token.status_code,
    "handled_gracefully": res_bad_token.status_code == 401,
}

# Test B: Concurrency Conflict on Case
res_conflict = client.post(
    "/api/v1/cases/CASE-2026-0001/transition",
    headers=auth_headers,
    json={"target_status": "CONFIRMED_FRAUD", "expected_version": 9999, "resolution_category": "TRUE_POSITIVE_FRAUD", "resolution_explanation": "Test explanation"},
)
failure_tests["concurrency_conflict"] = {
    "status_code": res_conflict.status_code,
    "handled_gracefully": res_conflict.status_code == 409,
}

results["failure_recovery"] = failure_tests

with open("benchmark_results.json", "w") as f:
    json.dump(results, f, indent=2)

print(json.dumps(results, indent=2))
