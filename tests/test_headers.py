"""Tests for IETF and RFC 6585 rate limiting HTTP headers."""

from apilimit.algorithms import RateLimitResult
from apilimit.headers import format_http_headers, format_raw_http_response


def test_headers_allowed():
    res = RateLimitResult(
        allowed=True,
        limit=60,
        remaining=42,
        reset=18,
        retry_after=0,
        policy="60;w=60",
        current_usage=18.0,
    )
    headers = format_http_headers(res)
    assert headers["RateLimit-Limit"] == "60"
    assert headers["RateLimit-Remaining"] == "42"
    assert headers["RateLimit-Reset"] == "18"
    assert headers["RateLimit-Policy"] == "60;w=60"
    assert "Retry-After" not in headers

    raw = format_raw_http_response(res)
    assert "HTTP/1.1 200 OK" in raw
    assert "RateLimit-Remaining: 42" in raw


def test_headers_rejected_429():
    res = RateLimitResult(
        allowed=False,
        limit=60,
        remaining=0,
        reset=25,
        retry_after=25,
        policy="60;w=60",
        current_usage=60.0,
    )
    headers = format_http_headers(res)
    assert headers["RateLimit-Remaining"] == "0"
    assert headers["Retry-After"] == "25"

    raw = format_raw_http_response(res)
    assert "HTTP/1.1 429 Too Many Requests" in raw
    assert "Retry-After: 25" in raw
