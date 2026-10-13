"""Ad campaign review, delivery grace and impression dedup (routes.marketing)."""

from types import SimpleNamespace

import routes.marketing as marketing


def _request(ip="203.0.113.7", ua="Mozilla/5.0"):
    return SimpleNamespace(
        headers={"user-agent": ua, "cf-connecting-ip": ip, "x-forwarded-for": ip},
        client=SimpleNamespace(host=ip),
    )


def test_serving_requires_admin_approval_and_grace_window():
    sql = marketing._SERVING_SQL
    assert "status = 'paid'" in sql
    assert "approved_at IS NOT NULL" in sql
    assert f"end_date + {marketing.AD_DELIVERY_GRACE_DAYS}" in sql
    assert "impressions_delivered < target_impressions" in sql


def test_visitor_hash_is_stable_and_distinguishes_visitors():
    a1 = marketing._visitor_hash(_request())
    a2 = marketing._visitor_hash(_request())
    b = marketing._visitor_hash(_request(ip="198.51.100.9"))
    assert a1 == a2
    assert a1 != b
    assert len(a1) == 32
    assert "203.0.113.7" not in a1


def test_review_state():
    assert marketing._review_state({"status": "rejected", "approved_at": None}) == "rejected"
    assert marketing._review_state({"status": "paid", "approved_at": None}) == "awaiting_review"
    assert marketing._review_state({"status": "paid", "approved_at": "2026-10-03"}) == "approved"
    assert marketing._review_state({"status": "completed", "approved_at": "2026-10-03"}) == "approved"
    assert marketing._review_state({"status": "pending", "approved_at": None}) == "not_paid"


def test_banner_mime_map_covers_accepted_formats():
    assert set(marketing._IMAGE_MIME) == {"PNG", "JPEG", "GIF", "WEBP"}


def test_admin_routes_registered():
    paths = {route.path for route in marketing.router.routes}
    assert "/marketing/ads/{ad_id}/image" in paths
    assert "/marketing/admin/campaigns" in paths
    assert "/marketing/admin/campaigns/{campaign_id}/approve" in paths
    assert "/marketing/admin/campaigns/{campaign_id}/reject" in paths
