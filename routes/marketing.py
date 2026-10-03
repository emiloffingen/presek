import io
import json
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
from core.image_service import _UPLOAD_ROOT
from core.limiter import custom_rate_limit
from routes.security import verify_csrf_token

log = logging.getLogger("presek")
router = APIRouter()

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

# Configure Stripe
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
MOCK_PAYMENTS_ENABLED = os.environ.get("MOCK_PAYMENTS_ENABLED", "false").lower() == "true"
STRIPE_CHECKOUT_ENABLED = os.environ.get("STRIPE_CHECKOUT_ENABLED", "false").lower() == "true"

# Pin the Stripe API version so an SDK upgrade can never silently change the
# payload shape we depend on. Defaults to the version bundled with stripe-python
# 15.3.0; override with STRIPE_API_VERSION when intentionally upgrading.
STRIPE_API_VERSION = os.environ.get("STRIPE_API_VERSION", "2026-06-24.dahlia").strip()
if STRIPE_API_VERSION:
    stripe.api_version = STRIPE_API_VERSION

# Stripe Managed Payments is enabled by default on this account and adds
# merchant-of-record/tax handling. Ad checkout is a plain card payment, so it is
# disabled by default; enabling it requires a product tax code.
MANAGED_PAYMENTS_ENABLED = os.environ.get("STRIPE_MANAGED_PAYMENTS_ENABLED", "false").lower() == "true"
STRIPE_PRODUCT_TAX_CODE = os.environ.get("STRIPE_PRODUCT_TAX_CODE", "").strip()

# Minimums enforced server-side so they cannot be bypassed by crafting requests.
# Must stay in sync with web/src/components/marketing/AdBookingForm.tsx.
MIN_CHARGE_CENTS = 3000  # €30 minimum cart value
MIN_DAILY_IMPRESSIONS = 2000

stripe.api_key = STRIPE_API_KEY

# CPM pricing. Base rates are benchmarked against MK news outlets (200-400 MKD
# CPM in their 2026 rate cards) and sit deliberately below that field, then the
# introductory promo discount is applied. Keep CPM_BASE_EUR / PROMO_DISCOUNT in
# sync with web/src/lib/adPricing.ts (the UI mirrors these numbers).
MKD_PER_EUR = 61.5
CPM_BASE_EUR = {
    "top_banner": 2.44,  # ~150 MKD — 990x80 / 990x150
    "sidebar": 2.93,  # ~180 MKD — 300x250 / 300x600
    "mobile_content": 3.25,  # ~200 MKD — 300x250
}


def _env_promo_discount() -> float:
    """Introductory discount from PROMO_DISCOUNT (0-0.95). Set 0 to end the promo."""
    try:
        value = float(os.environ.get("PROMO_DISCOUNT", "0.25"))
    except (TypeError, ValueError):
        return 0.25
    return min(max(value, 0.0), 0.95)


PROMO_DISCOUNT = _env_promo_discount()
CPM_RATES_EUR = {slot: round(rate * (1 - PROMO_DISCOUNT), 4) for slot, rate in CPM_BASE_EUR.items()}


def _amount_cents(slot_id: str, target_impressions: int) -> int:
    amount_eur = round((target_impressions / 1000.0) * CPM_RATES_EUR[slot_id], 2)
    return max(50, int(round(amount_eur * 100)))


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
    idempotency_key: str = Form(""),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    try:
        if not STRIPE_CHECKOUT_ENABLED:
            raise HTTPException(status_code=503, detail="Advertising checkout is temporarily unavailable")

        # 1. Validation
        # Validate email format
        if not EMAIL_REGEX.match(buyer_email):
            raise HTTPException(status_code=400, detail="Invalid email address format")

        # Validate target URL (prevent XSS / javascript protocols)
        parsed_url = urlparse(target_url)
        if parsed_url.scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="Target URL must start with http:// or https://")
        if not parsed_url.netloc:
            raise HTTPException(status_code=400, detail="Target URL must have a valid domain or host")

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

        # Enforce the same minimums the booking form applies client-side.
        num_days = (end_dt - start_dt).days + 1
        daily_avg = target_impressions / num_days
        if daily_avg < MIN_DAILY_IMPRESSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum average of {MIN_DAILY_IMPRESSIONS:,} impressions per day required",
            )

        amount_cents = _amount_cents(slot_id, target_impressions)
        if amount_cents < MIN_CHARGE_CENTS:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum checkout amount is €{MIN_CHARGE_CENTS / 100:.2f}",
            )

        if MANAGED_PAYMENTS_ENABLED and not STRIPE_PRODUCT_TAX_CODE:
            raise HTTPException(
                status_code=503,
                detail="Managed Payments requires STRIPE_PRODUCT_TAX_CODE",
            )

        # Validate file size (max 150KB)
        content = await file.read()
        if len(content) > 150 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds maximum allowed of 150KB")

        # Validate file extension
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            raise HTTPException(status_code=400, detail="Invalid file type. Only web images allowed")

        # Verify actual image content using Pillow
        try:
            image = Image.open(io.BytesIO(content))
            image.verify()
            if image.format not in ("PNG", "JPEG", "GIF", "WEBP"):
                raise HTTPException(status_code=400, detail="Invalid image content format")
        except Exception:
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

        # Idempotency: a client-supplied token lets retried submissions return the
        # original Stripe session instead of creating a duplicate campaign/charge.
        client_key = (idempotency_key or "").strip()[:120]
        if client_key:
            existing = await db.async_execute_one(
                "SELECT id, stripe_session_id FROM advertising_campaigns WHERE idempotency_key = %s",
                (client_key,),
            )
            if existing:
                existing_url = f"/marketing?status=success&campaign_id={existing['id']}"
                session_ref = str(existing["stripe_session_id"] or "")
                if session_ref and STRIPE_API_KEY and not session_ref.startswith("mock_"):
                    try:
                        prior = stripe.checkout.Session.retrieve(session_ref)
                        if "url" in prior and prior["url"]:
                            existing_url = prior["url"]
                    except Exception as retrieve_err:
                        log.warning(f"[marketing] idempotent session retrieve failed: {retrieve_err}")
                return {
                    "status": "success",
                    "checkout_url": existing_url,
                    "campaign_id": existing["id"],
                    "deduplicated": True,
                }

        # Reserve the campaign ID before creating the Stripe session so it can be
        # bound to Stripe metadata, but persist the file only after checkout succeeds.
        campaign_id = str(uuid.uuid4())
        safe_filename = f"{campaign_id}{ext}"
        # Serve through the image proxy: /static/uploads/* is only reachable from
        # the API (never from the public Astro origin), whereas /proxy is routed
        # to the API by the Cloudflare tunnel and accepts local /static paths.
        image_url = f"/proxy?url=/static/uploads/ads/{safe_filename}"

        idem_key = f"ad-checkout-{client_key or campaign_id}"

        # 4. Stripe Checkout Session Creation
        session_id = None
        checkout_url = f"/marketing?status=success&campaign_id={campaign_id}"

        if STRIPE_API_KEY:
            try:
                base_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.mk").rstrip("/")

                product_data = {
                    "name": f"Presek Banner Ad - {slot_id.replace('_', ' ').title()}",
                    "description": f"{target_impressions:,} impressions target from {start_date} to {end_date}",
                }
                if MANAGED_PAYMENTS_ENABLED:
                    product_data["tax_code"] = STRIPE_PRODUCT_TAX_CODE

                session = stripe.checkout.Session.create(
                    # payment_method_types is intentionally omitted: the account
                    # uses dynamic payment methods, and passing it is rejected
                    # when Managed Payments is active.
                    line_items=[
                        {
                            "price_data": {
                                "currency": "eur",
                                "product_data": product_data,
                                "unit_amount": amount_cents,
                            },
                            "quantity": 1,
                        }
                    ],
                    mode="payment",
                    # Ad checkout is a plain card payment; Managed Payments
                    # (MoR/tax) is opt-in via STRIPE_MANAGED_PAYMENTS_ENABLED.
                    managed_payments={"enabled": MANAGED_PAYMENTS_ENABLED},
                    success_url=f"{base_url}/marketing?status=success&campaign_id={campaign_id}",
                    cancel_url=f"{base_url}/marketing?status=cancel",
                    metadata={"campaign_id": campaign_id},
                    idempotency_key=idem_key,
                )
                session_id = session.id
                checkout_url = session.url
            except Exception as stripe_err:
                log.error(f"[marketing] Stripe checkout session creation failed: {stripe_err}")
                raise HTTPException(status_code=500, detail="Payment gateway session creation failed")
        elif MOCK_PAYMENTS_ENABLED and os.environ.get("ENV") in {"development", "test"}:
            # Explicit local-only mock mode. It must never be enabled on a public deployment.
            log.info("[marketing] No Stripe API Key configured. Emulating booking checkout bypass.")
            session_id = f"mock_session_{campaign_id}"
            status = "paid"
            checkout_url = f"/marketing?status=success&campaign_id={campaign_id}"
        else:
            log.error("[marketing] Stripe API key missing and mock payments are disabled")
            raise HTTPException(
                status_code=503,
                detail="Payment gateway is temporarily unavailable. Please try again later.",
            )

        upload_dir = os.path.join(_UPLOAD_ROOT, "ads")
        os.makedirs(upload_dir, exist_ok=True)
        with open(os.path.join(upload_dir, safe_filename), "wb") as f:
            f.write(content)

        status = "pending" if STRIPE_API_KEY else "paid"

        # 5. Save pending campaign to database
        sql = """
            INSERT INTO advertising_campaigns (
                id, buyer_name, buyer_email, slot_id, target_impressions,
                image_url, target_url, start_date, end_date, status,
                stripe_session_id, idempotency_key
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                client_key or None,
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
        raise HTTPException(status_code=400, detail="Missing signature or webhook configuration")

    try:
        # Verify the signature against the raw payload. construct_event returns a
        # StripeObject (no dict.get()), so after verification we re-parse the same
        # bytes into a plain dict and drive the handler with that.
        stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        event = json.loads(payload)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        session = event["data"]["object"]
        campaign_id = session.get("metadata", {}).get("campaign_id")
        session_id = session.get("id")

        if not campaign_id or not session_id or session.get("payment_status") != "paid":
            raise HTTPException(status_code=400, detail="Incomplete or unpaid checkout session")

        row = await db.async_execute_one(
            """
            SELECT id, stripe_session_id, status, slot_id, target_impressions
            FROM advertising_campaigns
            WHERE id = %s
            """,
            (campaign_id,),
        )
        if not row or row["stripe_session_id"] != session_id:
            raise HTTPException(status_code=400, detail="Checkout session does not match campaign")
        if session.get("mode") != "payment":
            raise HTTPException(status_code=400, detail="Unsupported checkout mode")
        if session.get("currency") != "eur":
            raise HTTPException(status_code=400, detail="Unexpected checkout currency")
        if session.get("amount_total") != _amount_cents(row["slot_id"], row["target_impressions"]):
            raise HTTPException(status_code=400, detail="Checkout amount does not match campaign")

        payment_intent = session.get("payment_intent")
        await db.async_execute(
            """
            UPDATE advertising_campaigns
            SET status = CASE WHEN status = 'pending' THEN 'paid' ELSE status END,
                stripe_payment_intent = COALESCE(%s, stripe_payment_intent)
            WHERE id = %s
            """,
            (payment_intent, campaign_id),
            fetch=False,
        )
        if row["status"] != "paid":
            log.info(f"[marketing] Ad campaign {campaign_id} successfully paid and activated.")

    elif event_type in {"checkout.session.async_payment_failed", "checkout.session.expired"}:
        session = event["data"]["object"]
        campaign_id = session.get("metadata", {}).get("campaign_id")
        session_id = session.get("id")
        if campaign_id and session_id:
            await db.async_execute(
                """
                UPDATE advertising_campaigns
                SET status = CASE WHEN %s = 'checkout.session.expired' THEN 'expired' ELSE 'failed' END
                WHERE id = %s AND stripe_session_id = %s AND status = 'pending'
                """,
                (event_type, campaign_id, session_id),
                fetch=False,
            )

    elif event_type in {"charge.refunded", "charge.dispute.created"}:
        # A fully refunded or disputed campaign must stop serving. Partial
        # refunds leave the campaign running (the customer still got value).
        charge = event["data"]["object"]
        payment_intent = charge.get("payment_intent")
        is_dispute = event_type == "charge.dispute.created"
        fully_refunded = bool(charge.get("refunded")) or (
            charge.get("amount") and charge.get("amount_refunded", 0) >= charge.get("amount")
        )
        if payment_intent and (is_dispute or fully_refunded):
            await db.async_execute(
                """
                UPDATE advertising_campaigns
                SET status = 'suspended'
                WHERE stripe_payment_intent = %s
                  AND status IN ('paid', 'completed')
                """,
                (payment_intent,),
                fetch=False,
            )
            log.info(f"[marketing] Campaign for payment_intent {payment_intent} suspended ({event_type}).")

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
        sql = """
            UPDATE advertising_campaigns
            SET clicks = clicks + 1
            WHERE id = %s
              AND status = 'paid'
              AND start_date <= CURRENT_DATE
              AND end_date >= CURRENT_DATE
              AND impressions_delivered < target_impressions
        """
        await db.async_execute(sql, (ad_id,), fetch=False)
        return {"status": "success"}
    except Exception as e:
        log.error(f"[marketing] Click tracking failed for {ad_id}: {e}")
        return {"status": "error"}


@router.post("/marketing/ads/{ad_id}/impression")
@custom_rate_limit("60/minute")
async def track_ad_impression(request: Request, ad_id: str, csrf_valid: bool = Depends(verify_csrf_token)):
    try:
        sql = """
            UPDATE advertising_campaigns
            SET impressions_delivered = impressions_delivered + 1
            WHERE id = %s
              AND status = 'paid'
              AND start_date <= CURRENT_DATE
              AND end_date >= CURRENT_DATE
              AND impressions_delivered < target_impressions
        """
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


@router.get("/marketing/campaign/{campaign_id}")
@custom_rate_limit("10/minute")
async def get_campaign_status(request: Request, campaign_id: str):
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
async def request_campaigns_access(
    request: Request, email: str = Form(...), csrf_valid: bool = Depends(verify_csrf_token)
):
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
            log.warning("[marketing] SMTP credentials not set. Cannot send access email.")

        return {
            "status": "success",
            "message": "Access links have been sent to your email.",
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"[marketing] Request access failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
