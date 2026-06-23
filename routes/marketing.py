import os
import uuid
import logging
import stripe
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import JSONResponse, RedirectResponse
from core.database import db_manager as db

log = logging.getLogger("presek")
router = APIRouter()

# Configure Stripe
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = STRIPE_API_KEY

# CPM Prices in EUR (converted from MKD at ~61.5 MKD/EUR)
# Display MKD equivalents on frontend for local context
MKD_PER_EUR = 61.5
CPM_RATES_EUR = {
    "top_banner": 1.00,      # ~60 MKD — 990x80 / 990x150
    "sidebar": 1.25,         # ~75 MKD — 300x250 / 300x600
    "mobile_content": 2.00,  # ~125 MKD — 300x250 / 800x200
}

@router.post("/marketing/checkout")
async def create_ad_checkout(
    request: Request,
    buyer_name: str = Form(...),
    buyer_email: str = Form(...),
    slot_id: str = Form(...),
    target_impressions: int = Form(...),
    target_url: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        # 1. Validation
        if slot_id not in CPM_RATES_EUR:
            raise HTTPException(status_code=400, detail="Invalid slot selection")

        if target_impressions < 1000:
            raise HTTPException(status_code=400, detail="Minimum target impressions is 1,000")

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")

        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="Start date must be before or equal to end date")

        # Validate file size (max 150KB)
        content = await file.read()
        if len(content) > 150 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds maximum allowed of 150KB")

        # Validate file extension
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            raise HTTPException(status_code=400, detail="Invalid file type. Only web images allowed")

        # 2. File Upload Persistence
        campaign_id = str(uuid.uuid4())
        upload_dir = "static/uploads/ads"
        os.makedirs(upload_dir, exist_ok=True)
        safe_filename = f"{campaign_id}{ext}"
        file_path = os.path.join(upload_dir, safe_filename)

        with open(file_path, "wb") as f:
            f.write(content)

        image_url = f"/static/uploads/ads/{safe_filename}"

        # 3. Pricing Calculation (in EUR)
        cpm_eur = CPM_RATES_EUR[slot_id]
        total_amount_eur = round((target_impressions / 1000.0) * cpm_eur, 2)
        if total_amount_eur < 0.50:  # Stripe minimum charge is €0.50
            total_amount_eur = 0.50

        # 4. Stripe Checkout Session Creation
        session_id = None
        checkout_url = f"/marketing?status=success&campaign_id={campaign_id}"

        if STRIPE_API_KEY:
            try:
                # Retrieve host to build callback URLs
                host = request.headers.get("host") or "presek.mk"
                proto = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
                base_url = f"{proto}://{host}"

                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    line_items=[{
                        "price_data": {
                            "currency": "eur",
                            "product_data": {
                                "name": f"Presek Banner Ad - {slot_id.replace('_', ' ').title()}",
                                "description": f"{target_impressions:,} impressions target from {start_date} to {end_date}",
                            },
                            "unit_amount": int(round(total_amount_eur * 100)),  # Stripe expects cents
                        },
                        "quantity": 1,
                    }],
                    mode="payment",
                    success_url=f"{base_url}/marketing?status=success&campaign_id={campaign_id}",
                    cancel_url=f"{base_url}/marketing?status=cancel",
                    metadata={"campaign_id": campaign_id},
                )
                session_id = session.id
                checkout_url = session.url
            except Exception as stripe_err:
                log.error(f"[marketing] Stripe checkout session creation failed: {stripe_err}")
                raise HTTPException(status_code=500, detail="Payment gateway session creation failed")
        else:
            # Development/Testing Sandbox fallback
            log.info("[marketing] No Stripe API Key configured. Emulating booking checkout bypass.")
            session_id = f"mock_session_{campaign_id}"
            # Automatically set status to 'paid' for developer sandbox if Stripe isn't configured
            status = "paid"
            checkout_url = f"/marketing?status=success&campaign_id={campaign_id}"
        
        status = "paid" if not STRIPE_API_KEY else "pending"

        # 5. Save pending campaign to database
        sql = """
            INSERT INTO advertising_campaigns (
                id, buyer_name, buyer_email, slot_id, target_impressions,
                image_url, target_url, start_date, end_date, status, stripe_session_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        await db.async_execute(
            sql,
            (
                campaign_id,
                buyer_name,
                buyer_email,
                slot_id,
                target_impressions,
                image_url,
                target_url,
                start_dt,
                end_dt,
                status,
                session_id
            ),
            fetch=False
        )

        return {"status": "success", "checkout_url": checkout_url, "campaign_id": campaign_id}

    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"[marketing] Booking creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/marketing/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header or not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Missing signature or webhook configuration")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        campaign_id = session.get("metadata", {}).get("campaign_id")
        session_id = session.get("id")

        if campaign_id:
            # Enforce webhook handler idempotency
            check_sql = "SELECT status FROM advertising_campaigns WHERE id = %s"
            row = await db.async_execute_one(check_sql, (campaign_id,))
            if row and row.get("status") == "paid":
                log.info(f"[marketing] Ad campaign {campaign_id} already marked as paid (webhook call ignored).")
            else:
                sql = "UPDATE advertising_campaigns SET status = 'paid' WHERE id = %s"
                await db.async_execute(sql, (campaign_id,), fetch=False)
                log.info(f"[marketing] Ad campaign {campaign_id} successfully paid and activated.")
        elif session_id:
            # Enforce webhook handler idempotency
            check_sql = "SELECT status FROM advertising_campaigns WHERE stripe_session_id = %s"
            row = await db.async_execute_one(check_sql, (session_id,))
            if row and row.get("status") == "paid":
                log.info(f"[marketing] Ad session {session_id} already marked as paid (webhook call ignored).")
            else:
                sql = "UPDATE advertising_campaigns SET status = 'paid' WHERE stripe_session_id = %s"
                await db.async_execute(sql, (session_id,), fetch=False)
                log.info(f"[marketing] Ad session {session_id} successfully paid and activated.")

    return {"status": "ok"}

@router.get("/marketing/ads/active")
async def get_active_ads():
    try:
        sql = """
            SELECT id, slot_id, image_url, target_url, impressions_delivered, target_impressions
            FROM advertising_campaigns
            WHERE status = 'paid'
              AND start_date <= CURRENT_DATE
              AND end_date >= CURRENT_DATE
              AND impressions_delivered < target_impressions
        """
        rows = await db.async_execute(sql)
        # Group by slot_id for easier consumption
        ads_by_slot = {}
        for row in rows:
            slot = row["slot_id"]
            if slot not in ads_by_slot:
                ads_by_slot[slot] = []
            ads_by_slot[slot].append({
                "id": row["id"],
                "image_url": row["image_url"],
                "target_url": row["target_url"],
            })
        return {"status": "success", "ads": ads_by_slot}
    except Exception as e:
        log.exception(f"[marketing] Active ads fetch failed: {e}")
        return {"status": "error", "ads": {}}

@router.post("/marketing/ads/{ad_id}/click")
async def track_ad_click(ad_id: str):
    try:
        sql = "UPDATE advertising_campaigns SET clicks = clicks + 1 WHERE id = %s"
        await db.async_execute(sql, (ad_id,), fetch=False)
        return {"status": "success"}
    except Exception as e:
        log.error(f"[marketing] Click tracking failed for {ad_id}: {e}")
        return {"status": "error"}

@router.post("/marketing/ads/{ad_id}/impression")
async def track_ad_impression(ad_id: str):
    try:
        sql = "UPDATE advertising_campaigns SET impressions_delivered = impressions_delivered + 1 WHERE id = %s"
        await db.async_execute(sql, (ad_id,), fetch=False)
        
        # Check if campaign target was reached to auto-complete
        check_sql = "SELECT impressions_delivered, target_impressions FROM advertising_campaigns WHERE id = %s"
        row = await db.async_execute_one(check_sql, (ad_id,))
        if row and row["impressions_delivered"] >= row["target_impressions"]:
            update_status_sql = "UPDATE advertising_campaigns SET status = 'completed' WHERE id = %s"
            await db.async_execute(update_status_sql, (ad_id,), fetch=False)
            log.info(f"[marketing] Ad campaign {ad_id} has reached its impression target and is completed.")
            
        return {"status": "success"}
    except Exception as e:
        log.error(f"[marketing] Impression tracking failed for {ad_id}: {e}")
        return {"status": "error"}
