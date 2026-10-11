"""Multi-Tenant Tiered Quotas and Tenant Profile Resolution.

Supports FREE, PRO, ENTERPRISE, and CUSTOM tiers with in-memory or SQLite caching.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from apilimit.algorithms import create_limiter


class Tier(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"
    CUSTOM = "CUSTOM"


@dataclass
class TenantQuota:
    tier: Tier
    rate_limit: int
    window_seconds: float = 60.0
    burst_capacity: int = 10

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "rate_limit": self.rate_limit,
            "window_seconds": self.window_seconds,
            "burst_capacity": self.burst_capacity,
        }


TIER_PROFILES: dict[Tier, TenantQuota] = {
    Tier.FREE: TenantQuota(tier=Tier.FREE, rate_limit=60, window_seconds=60.0, burst_capacity=10),
    Tier.PRO: TenantQuota(tier=Tier.PRO, rate_limit=600, window_seconds=60.0, burst_capacity=50),
    Tier.ENTERPRISE: TenantQuota(tier=Tier.ENTERPRISE, rate_limit=6000, window_seconds=60.0, burst_capacity=200),
}


class QuotaManager:
    """Manages tenant tier assignments and caches per-tenant rate limiters."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path) if db_path else None
        self._tenant_quotas: dict[str, TenantQuota] = {}
        self._limiters: dict[str, Any] = {}
        if self.db_path:
            self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tenant_quotas (
                    tenant_id TEXT PRIMARY KEY,
                    tier TEXT NOT NULL,
                    rate_limit INTEGER NOT NULL,
                    window_seconds REAL NOT NULL,
                    burst_capacity INTEGER NOT NULL
                )
                """
            )

    def set_quota(self, tenant_id: str, quota: TenantQuota) -> None:
        self._tenant_quotas[tenant_id] = quota
        # Clear cached limiter if quota changed
        self._limiters.pop(tenant_id, None)
        if self.db_path:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tenant_quotas (tenant_id, tier, rate_limit, window_seconds, burst_capacity)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                        tier=excluded.tier,
                        rate_limit=excluded.rate_limit,
                        window_seconds=excluded.window_seconds,
                        burst_capacity=excluded.burst_capacity
                    """,
                    (tenant_id, quota.tier.value, quota.rate_limit, quota.window_seconds, quota.burst_capacity),
                )

    def resolve_quota(self, tenant_id: str, requested_tier: str | None = None) -> TenantQuota:
        if requested_tier:
            tier_upper = requested_tier.upper()
            if tier_upper in Tier.__members__:
                t_enum = Tier[tier_upper]
                if t_enum in TIER_PROFILES:
                    return TIER_PROFILES[t_enum]

        if tenant_id in self._tenant_quotas:
            return self._tenant_quotas[tenant_id]

        if self.db_path:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT tier, rate_limit, window_seconds, burst_capacity FROM tenant_quotas WHERE tenant_id=?", (tenant_id,))
                row = cur.fetchone()
                if row:
                    q = TenantQuota(
                        tier=Tier(row[0]),
                        rate_limit=row[1],
                        window_seconds=row[2],
                        burst_capacity=row[3],
                    )
                    self._tenant_quotas[tenant_id] = q
                    return q

        # Default to Free tier on unrecognized tenant
        return TIER_PROFILES[Tier.FREE]

    def get_limiter(
        self,
        tenant_id: str,
        algorithm: str = "token_bucket",
        tier: str | None = None,
        now: float | None = None,
    ) -> Any:
        key = f"{tenant_id}:{algorithm}"
        if key not in self._limiters:
            quota = self.resolve_quota(tenant_id, requested_tier=tier)
            limiter = create_limiter(
                algorithm=algorithm,
                rate_or_limit=quota.rate_limit,
                burst_or_cap=quota.burst_capacity,
                window_seconds=quota.window_seconds,
                now=now,
            )
            self._limiters[key] = limiter
        return self._limiters[key]

    def reset(self, tenant_id: str | None = None, all_tenants: bool = False, now: float | None = None) -> None:
        """Resets rate limiting state for a tenant or all tenants. Idempotent."""
        if all_tenants:
            for limiter in self._limiters.values():
                limiter.reset(now=now)
            self._limiters.clear()
        elif tenant_id:
            # If tenant has active limiters, reset them
            for k in list(self._limiters.keys()):
                if k.startswith(f"{tenant_id}:"):
                    self._limiters[k].reset(now=now)
                    self._limiters.pop(k, None)
