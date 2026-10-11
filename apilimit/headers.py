"""IETF Draft RateLimit Header and RFC 6585 HTTP Response Serializer.
"""

from __future__ import annotations

from apilimit.algorithms import RateLimitResult


def format_http_headers(result: RateLimitResult) -> dict[str, str]:
    """Generates standard IETF RateLimit HTTP headers and RFC 6585 Retry-After header."""
    headers: dict[str, str] = {
        "RateLimit-Limit": str(result.limit),
        "RateLimit-Remaining": str(result.remaining),
        "RateLimit-Reset": str(result.reset),
        "RateLimit-Policy": result.policy,
    }

    if not result.allowed:
        headers["Retry-After"] = str(result.retry_after)

    return headers


def format_raw_http_response(result: RateLimitResult) -> str:
    """Formats full HTTP/1.1 status line and response headers."""
    if result.allowed:
        status_line = "HTTP/1.1 200 OK"
    else:
        status_line = "HTTP/1.1 429 Too Many Requests"

    headers = format_http_headers(result)
    header_lines = [f"{k}: {v}" for k, v in headers.items()]

    return f"{status_line}\n" + "\n".join(header_lines)
