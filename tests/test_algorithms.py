"""Tests for Token Bucket, Leaky Bucket, Sliding Window Counter, and Sliding Window Log."""

from apilimit.algorithms import (
    LeakyBucket,
    SlidingWindowCounter,
    SlidingWindowLog,
    TokenBucket,
    create_limiter,
)


def test_token_bucket_basic_flow():
    tb = TokenBucket(capacity=10.0, refill_rate=1.0, now=1000.0)

    # Consume 5 tokens
    res = tb.allow(cost=5, now=1000.0)
    assert res.allowed is True
    assert res.remaining == 5
    assert res.retry_after == 0

    # Consume remaining 5 tokens
    res2 = tb.allow(cost=5, now=1000.0)
    assert res2.allowed is True
    assert res2.remaining == 0

    # Empty bucket rejects
    res3 = tb.allow(cost=1, now=1000.0)
    assert res3.allowed is False
    assert res3.retry_after >= 1

    # Advance time by 3 seconds -> refills 3 tokens
    res4 = tb.allow(cost=2, now=1003.0)
    assert res4.allowed is True
    assert res4.remaining == 1


def test_token_bucket_cost_exceeds_capacity():
    """Edge Case #26: Request arriving with cost 15 when bucket capacity is 10 must be immediately rejected."""
    tb = TokenBucket(capacity=10.0, refill_rate=1.0, now=1000.0)
    res = tb.allow(cost=15, now=1000.0)
    assert res.allowed is False
    assert res.retry_after == 10  # Full refill time


def test_leaky_bucket_basic_flow():
    lb = LeakyBucket(capacity=5.0, leak_rate=1.0, now=1000.0)

    # Fill buffer to capacity
    res = lb.allow(cost=5, now=1000.0)
    assert res.allowed is True
    assert res.remaining == 0

    # Overflow buffer
    res_overflow = lb.allow(cost=1, now=1000.0)
    assert res_overflow.allowed is False
    assert res_overflow.retry_after >= 1

    # Leak 2 units of water over 2 seconds
    res_leak = lb.allow(cost=2, now=1002.0)
    assert res_leak.allowed is True


def test_sliding_window_counter_boundary_burst():
    """Edge Case #27: Prevents boundary burst 2x quota spike via weighted interpolation."""
    sw = SlidingWindowCounter(limit=10, window_seconds=60.0, now=1000.0)

    # Use 10 requests at end of window 1 (t = 1059.0)
    for _ in range(10):
        assert sw.allow(cost=1, now=1059.0).allowed is True

    # At start of window 2 (t = 1061.0, elapsed = 1.0s into new window)
    # Weight of prev window is (60 - 1) / 60 = 59/60 ~ 0.983
    # Estimated count ~ 10 * 0.983 ~ 9.83
    # Attempting to send 2 requests should be rejected!
    res_burst = sw.allow(cost=2, now=1061.0)
    assert res_burst.allowed is False
    assert res_burst.retry_after > 0


def test_sliding_window_log():
    swl = SlidingWindowLog(limit=3, window_seconds=10.0)
    now = 1000.0

    assert swl.allow(cost=1, now=now).allowed is True
    assert swl.allow(cost=1, now=now + 2).allowed is True
    assert swl.allow(cost=1, now=now + 4).allowed is True

    # 4th request within 10s window rejected
    assert swl.allow(cost=1, now=now + 5).allowed is False

    # After 11s, first request at t=1000 has expired
    assert swl.allow(cost=1, now=now + 11).allowed is True


def test_create_limiter_factory():
    l_tb = create_limiter("token_bucket", rate_or_limit=60, burst_or_cap=10)
    assert isinstance(l_tb, TokenBucket)

    l_lb = create_limiter("leaky_bucket", rate_or_limit=60, burst_or_cap=10)
    assert isinstance(l_lb, LeakyBucket)

    l_swc = create_limiter("sliding_window", rate_or_limit=60)
    assert isinstance(l_swc, SlidingWindowCounter)

    l_swl = create_limiter("sliding_log", rate_or_limit=60)
    assert isinstance(l_swl, SlidingWindowLog)
