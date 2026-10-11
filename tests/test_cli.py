"""Tests for apilimit CLI interface and exit codes."""

import json
from apilimit.cli import main


def test_cli_help():
    try:
        rc = main(["--help"])
    except SystemExit as exc:
        rc = exc.code
    assert rc == 0


def test_cli_invalid_command():
    rc = main(["invalid_action"])
    assert rc == 2


def test_cli_check_allowed(capsys):
    rc = main(["check", "--tenant", "test-user-1", "--tier", "free", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["allowed"] is True
    assert data["http_status"] == 200
    assert "RateLimit-Remaining" in data["headers"]


def test_cli_check_rate_limited(capsys):
    # Free tier burst capacity is 10; requesting cost 50 causes immediate rejection (HTTP 429)
    rc = main(["check", "--tenant", "test-user-burst", "--tier", "free", "--cost", "50", "--json"])
    assert rc == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["allowed"] is False
    assert data["http_status"] == 429
    assert "Retry-After" in data["headers"]


def test_cli_check_http_headers_format(capsys):
    rc = main(["check", "--tenant", "test-user-2", "--format", "http-headers"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "HTTP/1.1 200 OK" in captured.out
    assert "RateLimit-Limit:" in captured.out


def test_cli_bench(capsys):
    rc = main(["bench", "--tenant", "bench-cli", "--requests", "100", "--concurrency", "2", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total_requests"] == 100
    assert "throughput_req_per_sec" in data


def test_cli_inspect(capsys):
    rc = main(["inspect", "--tenant", "inspect-user", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["tenant"] == "inspect-user"


def test_cli_reset_idempotent(capsys):
    """Edge Case #28: Reset on tenant with zero prior requests is idempotent and succeeds."""
    rc = main(["reset", "--tenant", "brand-new-never-seen-tenant", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "RESET"


def test_cli_reset_all(capsys):
    rc = main(["reset", "--all", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["tenants"] == "ALL"
