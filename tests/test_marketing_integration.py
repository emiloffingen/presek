import os
import io
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from core.database import db_manager as db

@pytest.fixture
def client():
    from core.api_fast import app
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()

def test_checkout_validation_invalid_slot(client):
    # Prepare dummy file
    file_data = io.BytesIO(b"dummy image data")
    
    response = client.post(
        "/api/marketing/checkout",
        data={
            "buyer_name": "Test Buyer",
            "buyer_email": "buyer@example.com",
            "slot_id": "invalid_slot",
            "target_impressions": 10000,
            "target_url": "https://test.com",
            "start_date": "2026-06-25",
            "end_date": "2026-06-30"
        },
        files={"file": ("test.png", file_data, "image/png")}
    )
    assert response.status_code == 400
    assert "Invalid slot selection" in response.json()["detail"]

def test_checkout_validation_min_impressions(client):
    file_data = io.BytesIO(b"dummy image data")
    
    response = client.post(
        "/api/marketing/checkout",
        data={
            "buyer_name": "Test Buyer",
            "buyer_email": "buyer@example.com",
            "slot_id": "top_banner",
            "target_impressions": 500, # Too low (min is 1,000)
            "target_url": "https://test.com",
            "start_date": "2026-06-25",
            "end_date": "2026-06-30"
        },
        files={"file": ("test.png", file_data, "image/png")}
    )
    assert response.status_code == 400
    assert "Minimum target impressions" in response.json()["detail"]

def test_checkout_validation_large_file(client):
    # Create file larger than 150KB
    large_data = b"x" * (151 * 1024)
    file_data = io.BytesIO(large_data)
    
    response = client.post(
        "/api/marketing/checkout",
        data={
            "buyer_name": "Test Buyer",
            "buyer_email": "buyer@example.com",
            "slot_id": "top_banner",
            "target_impressions": 10000,
            "target_url": "https://test.com",
            "start_date": "2026-06-25",
            "end_date": "2026-06-30"
        },
        files={"file": ("test.png", file_data, "image/png")}
    )
    assert response.status_code == 400
    assert "File size exceeds maximum allowed of 150KB" in response.json()["detail"]

def test_checkout_and_ad_lifecycle(client):
    from unittest.mock import patch
    # Ensure tables are clean or we can query
    file_data = io.BytesIO(b"valid image data")
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    # 1. Success checkout flow (sandbox)
    with patch("routes.marketing.STRIPE_API_KEY", ""):
        response = client.post(
            "/api/marketing/checkout",
            data={
                "buyer_name": "Lifecycle Buyer",
                "buyer_email": "lifecycle@example.com",
                "slot_id": "top_banner",
                "target_impressions": 10000,
                "target_url": "https://lifecycle-test.com",
                "start_date": today,
                "end_date": tomorrow
            },
            files={"file": ("test.png", file_data, "image/png")}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "campaign_id" in data
    
    campaign_id = data["campaign_id"]
    
    # Verify database insertion
    campaign = db.execute("SELECT * FROM advertising_campaigns WHERE id = %s", (campaign_id,))
    assert len(campaign) == 1
    assert campaign[0]["buyer_name"] == "Lifecycle Buyer"
    assert campaign[0]["status"] == "paid" # sandbox autoplaces to paid if no STRIPE_API_KEY
    assert campaign[0]["impressions_delivered"] == 0
    assert campaign[0]["clicks"] == 0

    # 2. Get active ads and verify our campaign is active
    active_response = client.get("/api/marketing/ads/active")
    assert active_response.status_code == 200
    active_data = active_response.json()
    assert active_data["status"] == "success"
    assert "top_banner" in active_data["ads"]
    
    active_list = active_data["ads"]["top_banner"]
    campaign_active = [c for c in active_list if c["id"] == campaign_id]
    assert len(campaign_active) == 1
    assert campaign_active[0]["target_url"] == "https://lifecycle-test.com"

    # 3. Track impression
    imp_response = client.post(f"/api/marketing/ads/{campaign_id}/impression")
    assert imp_response.status_code == 200
    assert imp_response.json()["status"] == "success"
    
    # Verify impression incremented
    campaign = db.execute("SELECT impressions_delivered FROM advertising_campaigns WHERE id = %s", (campaign_id,))
    assert campaign[0]["impressions_delivered"] == 1

    # 4. Track click
    click_response = client.post(f"/api/marketing/ads/{campaign_id}/click")
    assert click_response.status_code == 200
    assert click_response.json()["status"] == "success"
    
    # Verify click incremented
    campaign = db.execute("SELECT clicks FROM advertising_campaigns WHERE id = %s", (campaign_id,))
    assert campaign[0]["clicks"] == 1
    
    # Clean up test database row
    db.execute("DELETE FROM advertising_campaigns WHERE id = %s", (campaign_id,))


def test_stripe_webhook_processing(client):
    from unittest.mock import patch
    
    mock_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"campaign_id": "test_campaign_id_123"},
                "id": "cs_test_123"
            }
        }
    }
    
    with patch("stripe.Webhook.construct_event", return_value=mock_event):
        with patch("routes.marketing.STRIPE_WEBHOOK_SECRET", "whsec_test"):
            # Set up a pending campaign in DB
            db.execute(
                """INSERT INTO advertising_campaigns (
                    id, buyer_name, buyer_email, slot_id, target_impressions,
                    image_url, target_url, start_date, end_date, status, stripe_session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    "test_campaign_id_123",
                    "Webhook Buyer",
                    "webhook@example.com",
                    "top_banner",
                    5000,
                    "/static/ads/test.png",
                    "https://webhook.com",
                    date.today(),
                    date.today(),
                    "pending",
                    "cs_test_123"
                )
            )
            
            response = client.post(
                "/api/marketing/webhook",
                json=mock_event,
                headers={"stripe-signature": "dummy_signature"}
            )
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            
            # Verify database updated to paid
            campaign = db.execute("SELECT status FROM advertising_campaigns WHERE id = %s", ("test_campaign_id_123",))
            assert campaign[0]["status"] == "paid"
            
            # Clean up
            db.execute("DELETE FROM advertising_campaigns WHERE id = %s", ("test_campaign_id_123",))


def test_stripe_webhook_idempotence(client):
    from unittest.mock import patch
    
    mock_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"campaign_id": "test_campaign_id_idemp"},
                "id": "cs_test_idemp"
            }
        }
    }
    
    with patch("stripe.Webhook.construct_event", return_value=mock_event):
        with patch("routes.marketing.STRIPE_WEBHOOK_SECRET", "whsec_test"):
            # Set up an already PAID campaign in DB
            db.execute(
                """INSERT INTO advertising_campaigns (
                    id, buyer_name, buyer_email, slot_id, target_impressions,
                    image_url, target_url, start_date, end_date, status, stripe_session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    "test_campaign_id_idemp",
                    "Webhook Buyer",
                    "webhook@example.com",
                    "top_banner",
                    5000,
                    "/static/ads/test.png",
                    "https://webhook.com",
                    date.today(),
                    date.today(),
                    "paid",
                    "cs_test_idemp"
                )
            )
            
            response = client.post(
                "/api/marketing/webhook",
                json=mock_event,
                headers={"stripe-signature": "dummy_signature"}
            )
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            
            # Verify status remains paid
            campaign = db.execute("SELECT status FROM advertising_campaigns WHERE id = %s", ("test_campaign_id_idemp",))
            assert campaign[0]["status"] == "paid"
            
            # Clean up
            db.execute("DELETE FROM advertising_campaigns WHERE id = %s", ("test_campaign_id_idemp",))

