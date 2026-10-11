# api-gateway-rate-limiter (`apilimit`)

High-Throughput API Gateway Rate Limiter supporting Token Bucket, Leaky Bucket, Sliding Window Counter, and Sliding Window Log algorithms, Multi-Tenant Tiered Quotas, and IETF / RFC 6585 HTTP rate-limiting headers. Built with zero external dependencies using the Python standard library.

## Features

- **4 Core Rate Limiting Algorithms**:
  - **Token Bucket**: Continuous burst refill rate limiting.
  - **Leaky Bucket**: Constant rate traffic smoothing and FIFO buffer overflow control.
  - **Sliding Window Counter**: Weighted interpolation across sliding window boundaries preventing boundary burst spikes.
  - **Sliding Window Log**: Timestamp-accurate moving window rate limiting.
- **Multi-Tenant Tiered Quotas**: Built-in support for `Free` (60 req/min, burst 10), `Pro` (600 req/min, burst 50), `Enterprise` (6000 req/min, burst 200), and `Custom` tiers.
- **IETF / RFC 6585 Standard Headers**: Emits standard `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, `RateLimit-Policy`, and `Retry-After` HTTP headers.
- **Concurrency Benchmarking**: Integrated multi-threaded load test engine measuring throughput (req/sec) and latency percentiles (p50, p95, p99).

## Installation

```bash
pip install -e .
```

## CLI Usage

### Rate Limit Checks
```bash
# Check quota with Token Bucket algorithm
apilimit check --tenant tenant-abc --algo token_bucket --tier pro

# Output as raw HTTP headers
apilimit check --tenant tenant-abc --format http-headers

# Check with custom rate and burst
apilimit check --tenant tenant-custom --tier custom --rate 120 --burst 30
```

### Concurrency Benchmark
```bash
apilimit bench --requests 5000 --concurrency 20 --algo sliding_window
```

### Inspection and Reset
```bash
# Inspect tenant usage state
apilimit inspect --tenant tenant-abc

# Reset quota usage
apilimit reset --tenant tenant-abc
apilimit reset --all
```

## License

MIT License. Copyright (c) 2026 aipd506.
