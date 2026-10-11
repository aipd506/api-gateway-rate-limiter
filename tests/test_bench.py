"""Tests for concurrency benchmark runner."""

from apilimit.bench import run_benchmark


def test_benchmark_execution():
    res = run_benchmark(
        tenant="test-bench",
        requests=500,
        concurrency=5,
        algo="token_bucket",
        rate=500,
        burst=200,
    )
    assert res["total_requests"] == 500
    assert res["allowed_requests"] + res["rejected_requests"] == 500
    assert res["throughput_req_per_sec"] > 0
    assert res["latency_p50_ms"] >= 0.0
    assert res["latency_p95_ms"] >= res["latency_p50_ms"]
