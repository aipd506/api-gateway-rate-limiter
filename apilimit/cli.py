"""CLI Entry Point for apilimit.

Subcommands: check, bench, inspect, reset.
Exit codes: 0 = Allowed / Success (200), 1 = Rate Limited (429), 2 = CLI argument error.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from apilimit.algorithms import create_limiter
from apilimit.bench import run_benchmark
from apilimit.headers import format_http_headers, format_raw_http_response
from apilimit.quotas import QuotaManager, TenantQuota, Tier

_GLOBAL_QUOTA_MANAGER = QuotaManager()


def _get_tenant_id(args: argparse.Namespace, required: bool = True) -> str | None:
    tid = getattr(args, "tenant", None) or getattr(args, "client", None)
    if not tid and required:
        sys.stderr.write("Error: Must specify either --tenant or --client identifier.\n")
        sys.exit(2)
    return tid


def _print_output(data: Any, as_json: bool = False, text_fallback: str | None = None) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    elif text_fallback is not None:
        print(text_fallback)
    elif isinstance(data, dict):
        for k, v in data.items():
            print(f"{k}: {v}")
    elif isinstance(data, list):
        for item in data:
            print(item)
    else:
        print(str(data))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apilimit",
        description="High-Throughput API Gateway Rate Limiter with RFC HTTP Headers",
    )
    parser.add_argument("--version", action="version", version="apilimit 0.1.0")

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. check
    check_p = subparsers.add_parser("check", help="Evaluate rate limit for a request")
    check_p.add_argument("--tenant", "--client", dest="tenant", help="Tenant or client ID")
    check_p.add_argument(
        "--algo",
        "--algorithm",
        dest="algorithm",
        default="token_bucket",
        help="Algorithm (token_bucket, leaky_bucket, sliding_window, sliding_log)",
    )
    check_p.add_argument(
        "--tier",
        choices=["free", "pro", "enterprise", "custom"],
        default="free",
        help="Quota tier",
    )
    check_p.add_argument("--rate", type=int, help="Custom rate limit")
    check_p.add_argument("--burst", type=int, help="Custom burst capacity")
    check_p.add_argument("--cost", type=int, default=1, help="Request token cost")
    check_p.add_argument("--db", help="Path to SQLite persistent database")
    check_p.add_argument(
        "--format",
        choices=["json", "http-headers", "text"],
        default="json",
        help="Output format",
    )
    check_p.add_argument("--json", action="store_true", help="Output as JSON")

    # 2. bench
    bench_p = subparsers.add_parser("bench", help="Execute multi-threaded concurrency benchmark")
    bench_p.add_argument("--tenant", "--client", dest="tenant", default="bench-tenant", help="Tenant ID")
    bench_p.add_argument("--requests", type=int, default=1000, help="Total requests count")
    bench_p.add_argument("--concurrency", type=int, default=10, help="Concurrent workers")
    bench_p.add_argument("--algo", default="token_bucket", help="Rate limiting algorithm")
    bench_p.add_argument("--rate", type=int, default=1000, help="Rate limit per minute")
    bench_p.add_argument("--burst", type=int, default=500, help="Burst capacity")
    bench_p.add_argument("--memory", action="store_true", default=True, help="In-memory benchmark")
    bench_p.add_argument("--json", action="store_true", help="Output as JSON")

    # 3. inspect
    insp_p = subparsers.add_parser("inspect", help="Inspect current tenant rate limit state")
    insp_p.add_argument("--tenant", "--client", dest="tenant", required=True, help="Tenant ID")
    insp_p.add_argument("--algo", default="token_bucket", help="Rate limiting algorithm")
    insp_p.add_argument("--db", help="Path to SQLite database")
    insp_p.add_argument("--format", choices=["json", "table"], default="json", help="Output format")
    insp_p.add_argument("--json", action="store_true", help="Output as JSON")

    # 4. reset
    reset_p = subparsers.add_parser("reset", help="Reset rate limit usage for a tenant")
    reset_group = reset_p.add_mutually_exclusive_group(required=True)
    reset_group.add_argument("--tenant", "--client", dest="tenant", help="Tenant ID")
    reset_group.add_argument("--all", action="store_true", help="Reset all tenants")
    reset_p.add_argument("--db", help="Path to SQLite database")
    reset_p.add_argument("--json", action="store_true", help="Output as JSON")

    return parser


def handle_check(args: argparse.Namespace) -> int:
    tenant_id = _get_tenant_id(args, required=True)
    qm = QuotaManager(db_path=args.db) if args.db else _GLOBAL_QUOTA_MANAGER

    if args.tier == "custom" and (args.rate or args.burst):
        rate = args.rate or 60
        burst = args.burst or 10
        qm.set_quota(tenant_id, TenantQuota(tier=Tier.CUSTOM, rate_limit=rate, burst_capacity=burst))

    limiter = qm.get_limiter(tenant_id=tenant_id, algorithm=args.algorithm, tier=args.tier)
    res = limiter.allow(cost=args.cost)

    output_data = res.to_dict()
    output_data["headers"] = format_http_headers(res)
    output_data["http_status"] = 200 if res.allowed else 429

    use_json = args.json or (args.format == "json")
    if use_json:
        _print_output(output_data, as_json=True)
    elif args.format == "http-headers":
        print(format_raw_http_response(res))
    else:
        status_text = "ALLOWED (HTTP 200)" if res.allowed else f"RATE LIMITED (HTTP 429, retry after {res.retry_after}s)"
        print(f"Status: {status_text}")
        print(f"Remaining: {res.remaining}/{res.limit}")
        print(f"Reset: {res.reset}s")

    return 0 if res.allowed else 1


def handle_bench(args: argparse.Namespace) -> int:
    tenant_id = args.tenant or "bench-tenant"
    summary = run_benchmark(
        tenant=tenant_id,
        requests=args.requests,
        concurrency=args.concurrency,
        algo=args.algo,
        rate=args.rate,
        burst=args.burst,
        use_memory=args.memory,
    )
    _print_output(summary, as_json=args.json or True)
    return 0


def handle_inspect(args: argparse.Namespace) -> int:
    tenant_id = _get_tenant_id(args, required=True)
    qm = QuotaManager(db_path=args.db) if args.db else _GLOBAL_QUOTA_MANAGER
    limiter = qm.get_limiter(tenant_id=tenant_id, algorithm=args.algo)
    state = limiter.inspect()
    state["tenant"] = tenant_id

    _print_output(state, as_json=args.json or True)
    return 0


def handle_reset(args: argparse.Namespace) -> int:
    qm = QuotaManager(db_path=args.db) if args.db else _GLOBAL_QUOTA_MANAGER
    if args.all:
        qm.reset(all_tenants=True)
        _print_output({"status": "RESET", "tenants": "ALL"}, as_json=args.json, text_fallback="Reset all tenant rate limits.")
    else:
        tenant_id = _get_tenant_id(args, required=True)
        qm.reset(tenant_id=tenant_id)
        _print_output({"status": "RESET", "tenant": tenant_id}, as_json=args.json, text_fallback=f"Reset rate limits for tenant {tenant_id}.")
    return 0


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        parsed = parser.parse_args(args)
    except SystemExit as exc:
        return exc.code

    if parsed.subcommand == "check":
        return handle_check(parsed)
    elif parsed.subcommand == "bench":
        return handle_bench(parsed)
    elif parsed.subcommand == "inspect":
        return handle_inspect(parsed)
    elif parsed.subcommand == "reset":
        return handle_reset(parsed)

    return 2


if __name__ == "__main__":
    sys.exit(main())
