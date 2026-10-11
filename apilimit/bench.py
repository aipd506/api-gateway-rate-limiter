"""Multi-Threaded Concurrency Benchmark Runner for Rate Limiters.

Measures throughput (req/sec) and latency percentiles (p50, p95, p99).
"""

from __future__ import annotations

import statistics
import threading
import time
from typing import Any

from apilimit.algorithms import create_limiter


def run_benchmark(
    tenant: str = "bench-tenant",
    requests: int = 1000,
    concurrency: int = 10,
    algo: str = "token_bucket",
    rate: int = 1000,
    burst: int = 500,
    use_memory: bool = True,
) -> dict[str, Any]:
    """Runs a multi-threaded load test on the specified rate limiting algorithm."""
    limiter = create_limiter(
        algorithm=algo,
        rate_or_limit=rate,
        burst_or_cap=burst,
    )

    reqs_per_thread = requests // max(1, concurrency)
    actual_total = reqs_per_thread * concurrency

    latencies_ms: list[float] = []
    allowed_count = 0
    rejected_count = 0
    lock = threading.Lock()

    def worker():
        nonlocal allowed_count, rejected_count
        local_latencies: list[float] = []
        local_allowed = 0
        local_rejected = 0

        for _ in range(reqs_per_thread):
            t0 = time.perf_counter()
            res = limiter.allow(cost=1)
            t1 = time.perf_counter()

            latency_ms = (t1 - t0) * 1000.0
            local_latencies.append(latency_ms)

            if res.allowed:
                local_allowed += 1
            else:
                local_rejected += 1

        with lock:
            latencies_ms.extend(local_latencies)
            allowed_count += local_allowed
            rejected_count += local_rejected

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]

    start_time = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    elapsed_time = time.perf_counter() - start_time

    # Calculate percentiles
    if latencies_ms:
        latencies_sorted = sorted(latencies_ms)
        n = len(latencies_sorted)
        p50 = latencies_sorted[int(0.50 * (n - 1))]
        p95 = latencies_sorted[int(0.95 * (n - 1))]
        p99 = latencies_sorted[int(0.99 * (n - 1))]
        avg_lat = statistics.mean(latencies_sorted)
    else:
        p50 = p95 = p99 = avg_lat = 0.0

    throughput = actual_total / max(elapsed_time, 0.0001)

    return {
        "tenant": tenant,
        "algorithm": algo,
        "concurrency": concurrency,
        "total_requests": actual_total,
        "allowed_requests": allowed_count,
        "rejected_requests": rejected_count,
        "elapsed_seconds": round(elapsed_time, 4),
        "throughput_req_per_sec": round(throughput, 2),
        "latency_avg_ms": round(avg_lat, 4),
        "latency_p50_ms": round(p50, 4),
        "latency_p95_ms": round(p95, 4),
        "latency_p99_ms": round(p99, 4),
    }
