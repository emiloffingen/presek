import io
import logging
import os
import re
import uuid
from datetime import datetime
from urllib.parse import urlparse

import stripe
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from PIL import Image

from core.database import db_manager as db
from core.limiter import custom_rate_limit
from routes.security import verify_csrf_token

log = logging.getLogger("presek")
router = APIRouter()

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

# Configure Stripe
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = STRIPE_API_KEY

# CPM Prices in EUR (converted from MKD at ~61.5 MKD/EUR)
# Display MKD equivalents on frontend for local context
# Adjusted to achieve exactly 50% savings vs traditional media rates
MKD_PER_EUR = 61.5
CPM_RATES_EUR = {
    "top_banner": 0.9756,  # 60 MKD exactly — 990x80 / 990x150 (50% of 120 MKD)
    "sidebar": 1.2207,  # 75 MKD exactly — 300x250 / 300x600 (50% of 150 MKD)
    "mobile_content": 2.00,  # 125 MKD — 300x250 / 800x200 (50% of 250 MKD)
}


@router.post("/marketing/checkout")
@custom_rate_limit("5/minute")
async def create_ad_checkout(
    request: Request,
    buyer_name: str = Form(...),
    buyer_email: str = Form(...),
    slot_id: str = Form(...),
    target_impressions: int = Form(...),
    target_url: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    file: UploadFile = File(...),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    try:
        # 1. Validation
        # Validate email format
        if not EMAIL_REGEX.match(buyer_email):
            raise HTTPException(status_code=400, detail="Invalid email address format")

        # Validate target URL (prevent XSS / javascript protocols)
        parsed_url = urlparse(target_url)
        if parsed_url.scheme not in ("http", "https"):
            raise HTTPException(
                status_code=400, detail="Target URL must start with http:// or https://"
            )
        if not parsed_url.netloc:
            raise HTTPException(
                status_code=400, detail="Target URL must have a valid domain or host"
            )

        if slot_id not in CPM_RATES_EUR:
            raise HTTPException(status_code=400, detail="Invalid slot selection")

        if target_impressions < 1000:
            raise HTTPException(
                status_code=400, detail="Minimum target impressions is 1,000"
            )

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format, use YYYY-MM-DD"
            )

        if start_dt > end_dt:
            raise HTTPException(
                status_code=400, detail="Start date must be before or equal to end date"
            )

        # Validate file size (max 150KB)
        content = await file.read()
        if len(content) > 150 * 1024:
            raise HTTPException(
                status_code=400, detail="File size exceeds maximum allowed of 150KB"
            )

        # Validate file extension
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            raise HTTPException(
                status_code=400, detail="Invalid file type. Only web images allowed"
            )

        # Verify actual image content using Pillow
        try:
            image = Image.open(io.BytesIO(content))
            image.verify()
            if image.format not in ("PNG", "JPEG", "GIF", "WEBP"):
                raise HTTPException(
                    status_code=400, detail="Invalid image content format"
                )
        except Exception:
            raise HTTPException(
                status_code=400, detail="Uploaded file is not a valid image"
            )

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
                base_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.mk").rstrip("/")

                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    line_items=[
                        {
                            "price_data": {
                                "currency": "eur",
                                "product_data": {
                                    "name": f"Presek Banner Ad - {slot_id.replace('_', ' ').title()}",
                                    "description": f"{target_impressions:,} impressions target from {start_date} to {end_date}",
                                },
                                "unit_amount": int(
                                    round(total_amount_eur * 100)
                                ),  # Stripe expects cents
                            },
                            "quantity": 1,
                        }
                    ],
                    mode="payment",
                    success_url=f"{base_url}/marketing?status=success&campaign_id={campaign_id}",
                    cancel_url=f"{base_url}/marketing?status=cancel",
                    metadata={"campaign_id": campaign_id},
                )
                session_id = session.id
                checkout_url = session.url
            except Exception as stripe_err:
                log.error(
                    f"[marketing] Stripe checkout session creation failed: {stripe_err}"
                )
                raise HTTPException(
                    status_code=500, detail="Payment gateway session creation failed"
                )
        else:
            # Sandbox bypass is strictly forbidden in production to prevent fraud
            if os.environ.get("ENV") == "production":
                log.error(
                    "[marketing] Stripe API key missing in production environment!"
                )
                raise HTTPException(
                    status_code=500,
                    detail="Payment gateway is misconfigured. Please contact support.",
                )

            # Development/Testing Sandbox fallback
            log.info(
                "[marketing] No Stripe API Key configured. Emulating booking checkout bypass."
            )
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
                session_id,
            ),
            fetch=False,
        )

        return {
            "status": "success",
            "checkout_url": checkout_url,
            "campaign_id": campaign_id,
        }

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
        raise HTTPException(
            status_code=400, detail="Missing signature or webhook configuration"
        )

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
                log.info(
                    f"[marketing] Ad campaign {campaign_id} already marked as paid (webhook call ignored)."
                )
            else:
                sql = "UPDATE advertising_campaigns SET status = 'paid' WHERE id = %s"
                await db.async_execute(sql, (campaign_id,), fetch=False)
                log.info(
                    f"[marketing] Ad campaign {campaign_id} successfully paid and activated."
                )
        elif session_id:
            # Enforce webhook handler idempotency
            check_sql = (
                "SELECT status FROM advertising_campaigns WHERE stripe_session_id = %s"
            )
            row = await db.async_execute_one(check_sql, (session_id,))
            if row and row.get("status") == "paid":
                log.info(
                    f"[marketing] Ad session {session_id} already marked as paid (webhook call ignored)."
                )
            else:
                sql = "UPDATE advertising_campaigns SET status = 'paid' WHERE stripe_session_id = %s"
                await db.async_execute(sql, (session_id,), fetch=False)
                log.info(
                    f"[marketing] Ad session {session_id} successfully paid and activated."
                )

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
            ads_by_slot[slot].append(
                {
                    "id": row["id"],
                    "image_url": row["image_url"],
                    "target_url": row["target_url"],
                }
            )
        return {"status": "success", "ads": ads_by_slot}
    except Exception as e:
        log.exception(f"[marketing] Active ads fetch failed: {e}")
        return {"status": "error", "ads": {}}


@router.post("/marketing/ads/{ad_id}/click")
@custom_rate_limit("20/minute")
async def track_ad_click(request: Request, ad_id: str, csrf_valid: bool = Depends(verify_csrf_token)):
    try:
        sql = "UPDATE advertising_campaigns SET clicks = clicks + 1 WHERE id = %s"
        await db.async_execute(sql, (ad_id,), fetch=False)
        return {"status": "success"}
    except Exception as e:
        log.error(f"[marketing] Click tracking failed for {ad_id}: {e}")
        return {"status": "error"}


@router.post("/marketing/ads/{ad_id}/impression")
@custom_rate_limit("60/minute")
async def track_ad_impression(request: Request, ad_id: str, csrf_valid: bool = Depends(verify_csrf_token)):
    try:
        sql = "UPDATE advertising_campaigns SET impressions_delivered = impressions_delivered + 1 WHERE id = %s"
        await db.async_execute(sql, (ad_id,), fetch=False)

        # Check if campaign target was reached to auto-complete
        check_sql = "SELECT impressions_delivered, target_impressions FROM advertising_campaigns WHERE id = %s"
        row = await db.async_execute_one(check_sql, (ad_id,))
        if row and row["impressions_delivered"] >= row["target_impressions"]:
            update_status_sql = (
                "UPDATE advertising_campaigns SET status = 'completed' WHERE id = %s"
            )
            await db.async_execute(update_status_sql, (ad_id,), fetch=False)
            log.info(
                f"[marketing] Ad campaign {ad_id} has reached its impression target and is completed."
            )

        return {"status": "success"}
    except Exception as e:
        log.error(f"[marketing] Impression tracking failed for {ad_id}: {e}")
        return {"status": "error"}


@router.get("/marketing/campaign/{campaign_id}")
async def get_campaign_status(campaign_id: str):
    try:
        sql = """
            SELECT id, buyer_name, buyer_email, slot_id, target_impressions,
                   impressions_delivered, clicks, start_date, end_date, status, image_url, target_url
            FROM advertising_campaigns
            WHERE id = %s
        """
        row = await db.async_execute_one(sql, (campaign_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Campaign not found")

        return {
            "status": "success",
            "campaign": {
                "id": row["id"],
                "buyer_name": row["buyer_name"],
                "slot_id": row["slot_id"],
                "target_impressions": row["target_impressions"],
                "impressions_delivered": row["impressions_delivered"],
                "clicks": row["clicks"],
                "start_date": row["start_date"].isoformat(),
                "end_date": row["end_date"].isoformat(),
                "status": row["status"],
                "image_url": row["image_url"],
                "target_url": row["target_url"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"[marketing] Get campaign status failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/marketing/request-access")
@custom_rate_limit("3/minute")
async def request_campaigns_access(request: Request, email: str = Form(...), csrf_valid: bool = Depends(verify_csrf_token)):
    try:
        # Validate email
        if not EMAIL_REGEX.match(email):
            raise HTTPException(status_code=400, detail="Invalid email address format")

        # Find all campaigns for this email
        sql = "SELECT id, slot_id, status FROM advertising_campaigns WHERE buyer_email = %s"
        rows = await db.async_execute(sql, (email,))
        if not rows:
            # Return generic success to avoid email enumeration
            return {
                "status": "success",
                "message": "If campaigns exist for this email, an access link has been sent.",
            }

        # Build access link overview
        base_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.live").rstrip("/")

        email_content = "<h2>Presek Marketing Access Link</h2>"
        email_content += "<p>Hello, you requested access links to your advertising campaigns on Presek.</p>"
        email_content += "<p>Below are your registered campaigns:</p><ul>"

        for row in rows:
            camp_id = row["id"]
            slot = row["slot_id"].replace("_", " ").title()
            status = row["status"].upper()
            link = f"{base_url}/marketing/status?id={camp_id}"
            email_content += f"<li><strong>{slot}</strong> (Status: {status}) - <a href='{link}'>{link}</a></li>"

        email_content += "</ul><br/><p>If you did not request this email, you can safely ignore it.</p>"

        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")

        if smtp_user and smtp_pass:
            from tasks.utils import send_email

            subject = "Your Presek Ad Campaigns Access Links"
            send_email(email_content, subject, smtp_user, smtp_pass, email)
            log.info(f"[marketing] Sent access email successfully to {email}")
        else:
            log.warning(
                "[marketing] SMTP credentials not set. Cannot send access email."
            )

        return {
            "status": "success",
            "message": "Access links have been sent to your email.",
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"[marketing] Request access failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
