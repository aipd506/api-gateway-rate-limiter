"""Tests for multi-tenant tiered quotas and QuotaManager."""

from apilimit.quotas import QuotaManager, TenantQuota, Tier


def test_default_to_free_tier():
    qm = QuotaManager()
    quota = qm.resolve_quota("unknown_tenant_123")
    assert quota.tier == Tier.FREE
    assert quota.rate_limit == 60
    assert quota.burst_capacity == 10


def test_explicit_tier_resolution():
    qm = QuotaManager()
    pro_quota = qm.resolve_quota("pro_tenant", requested_tier="pro")
    assert pro_quota.tier == Tier.PRO
    assert pro_quota.rate_limit == 600
    assert pro_quota.burst_capacity == 50

    ent_quota = qm.resolve_quota("ent_tenant", requested_tier="enterprise")
    assert ent_quota.tier == Tier.ENTERPRISE
    assert ent_quota.rate_limit == 6000
    assert ent_quota.burst_capacity == 200


def test_custom_quota():
    qm = QuotaManager()
    qm.set_quota(
        "custom_user",
        TenantQuota(tier=Tier.CUSTOM, rate_limit=120, burst_capacity=25, window_seconds=30.0),
    )
    resolved = qm.resolve_quota("custom_user")
    assert resolved.tier == Tier.CUSTOM
    assert resolved.rate_limit == 120
    assert resolved.burst_capacity == 25


def test_sqlite_backed_quota_manager(tmp_path):
    db_file = tmp_path / "quotas.db"
    qm1 = QuotaManager(db_path=db_file)
    qm1.set_quota("tenant_db", TenantQuota(tier=Tier.PRO, rate_limit=800, burst_capacity=60))

    qm2 = QuotaManager(db_path=db_file)
    resolved = qm2.resolve_quota("tenant_db")
    assert resolved.tier == Tier.PRO
    assert resolved.rate_limit == 800
