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
    # Ensure tables are clean or we can query
    file_data = io.BytesIO(b"valid image data")
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    
    # 1. Success checkout flow (sandbox)
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
