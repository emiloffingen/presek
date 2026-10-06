import hashlib
import io
import json
import logging
import os
import random
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import stripe
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from PIL import Image

from core.database import db_manager as db
from core.limiter import custom_rate_limit
from routes.admin import verify_admin
from routes.common import _client_ip_for_request
from routes.security import verify_csrf_token

log = logging.getLogger("presek")
router = APIRouter()

# Short TTL in-process cache for the ad-slot lookup. The storefront SSR calls
# this endpoint on every render; the payload changes only when campaigns change,
# so a small TTL removes the repeated DB round-trip without staleness concerns.
_ADS_CACHE = {"data": None, "ts": 0.0}
_ADS_CACHE_TTL = int(os.environ.get("MARKETING_ADS_CACHE_TTL", "60"))

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


# A campaign that has not delivered its impressions by end_date keeps serving for
# this many extra days before it is flagged for a partial refund.
AD_DELIVERY_GRACE_DAYS = max(0, int(os.environ.get("AD_DELIVERY_GRACE_DAYS", "14")))

# Paid, approved by an admin, started, inside end_date + grace, impressions left.
_SERVING_SQL = f"""
    status = 'paid'
    AND approved_at IS NOT NULL
    AND start_date <= CURRENT_DATE
    AND CURRENT_DATE <= end_date + {AD_DELIVERY_GRACE_DAYS}
    AND impressions_delivered < target_impressions
"""

_IMAGE_MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}


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
            image_format = image.format
        except Exception:
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")
        if image_format not in _IMAGE_MIME:
            raise HTTPException(status_code=400, detail="Invalid image content format")

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
        # The banner is stored in the DB and served by any host from this URL.
        image_url = f"/api/marketing/ads/{campaign_id}/image"

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

        status = "pending" if STRIPE_API_KEY else "paid"

        # 5. Save pending campaign to database
        sql = """
            INSERT INTO advertising_campaigns (
                id, buyer_name, buyer_email, slot_id, target_impressions,
                image_url, target_url, start_date, end_date, status,
                stripe_session_id, idempotency_key, image_data, image_mime
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                content,
                _IMAGE_MIME[image_format],
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
            # Paid campaigns wait for an admin to approve the banner and link.
            log.warning(f"[marketing] Ad campaign {campaign_id} paid; awaiting review before it serves.")

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
async def get_active_ads(response: Response):
    response.headers["Cache-Control"] = f"public, max-age={_ADS_CACHE_TTL}"
    now = time.time()
    cached = _ADS_CACHE["data"]
    if cached is not None and (now - _ADS_CACHE["ts"]) < _ADS_CACHE_TTL:
        return cached
    try:
        sql = f"""
            SELECT id, slot_id, image_url, target_url, impressions_delivered, target_impressions
            FROM advertising_campaigns
            WHERE {_SERVING_SQL}
        """  # nosec B608 - only module constants are interpolated; values are bound params
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
        result = {"status": "success", "ads": ads_by_slot}
        _ADS_CACHE["data"] = result
        _ADS_CACHE["ts"] = time.time()
        return result
    except Exception as e:
        log.exception(f"[marketing] Active ads fetch failed: {e}")
        return {"status": "error", "ads": {}}


def _visitor_hash(request: Request) -> str:
    """Daily-rotating, non-reversible visitor key for impression dedup."""
    secret = os.environ.get("CSRF_TOKEN_SECRET") or os.environ.get("SECRET_KEY") or ""
    raw = "|".join(
        (
            secret,
            _client_ip_for_request(request),
            request.headers.get("user-agent", ""),
            datetime.now(timezone.utc).date().isoformat(),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@router.get("/marketing/ads/{ad_id}/image")
@custom_rate_limit("120/minute")
async def get_ad_image(request: Request, ad_id: str):
    row = await db.async_execute_one(
        "SELECT image_data, image_mime FROM advertising_campaigns WHERE id = %s AND status <> 'rejected'",
        (ad_id,),
    )
    if not row or not row["image_data"]:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(
        content=bytes(row["image_data"]),
        media_type=row["image_mime"] or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/marketing/ads/{ad_id}/click")
@custom_rate_limit("20/minute")
async def track_ad_click(request: Request, ad_id: str, csrf_valid: bool = Depends(verify_csrf_token)):
    try:
        sql = f"""
            UPDATE advertising_campaigns
            SET clicks = clicks + 1
            WHERE id = %s AND {_SERVING_SQL}
        """  # nosec B608 - only module constants are interpolated; values are bound params
        await db.async_execute(sql, (ad_id,), fetch=False)
        return {"status": "success"}
    except Exception as e:
        log.error(f"[marketing] Click tracking failed for {ad_id}: {e}")
        return {"status": "error"}


@router.post("/marketing/ads/{ad_id}/impression")
@custom_rate_limit("60/minute")
async def track_ad_impression(request: Request, ad_id: str, csrf_valid: bool = Depends(verify_csrf_token)):
    try:
        # Count each visitor at most once per campaign per day: the seen-row is
        # inserted only for a serving campaign, and the counter moves only when
        # that insert actually added a row.
        sql = f"""
            WITH seen AS (
                INSERT INTO ad_impression_seen (campaign_id, visitor_hash, day)
                SELECT id, %s, CURRENT_DATE FROM advertising_campaigns
                WHERE id = %s AND {_SERVING_SQL}
                ON CONFLICT DO NOTHING
                RETURNING campaign_id
            )
            UPDATE advertising_campaigns
            SET impressions_delivered = impressions_delivered + 1
            WHERE id IN (SELECT campaign_id FROM seen)
        """  # nosec B608 - only module constants are interpolated; values are bound params
        # read_only=False: the WITH prefix would otherwise route this write to the replica.
        await db.async_execute(sql, (_visitor_hash(request), ad_id), fetch=False, read_only=False)
        if random.random() < 0.002:
            await db.async_execute("DELETE FROM ad_impression_seen WHERE day < CURRENT_DATE - 2", fetch=False)

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
                   impressions_delivered, clicks, start_date, end_date, status, image_url, target_url,
                   approved_at, review_note
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
                "review": _review_state(row),
                "review_note": row["review_note"] if row["status"] == "rejected" else None,
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

        # Same response as the no-campaigns branch so the endpoint cannot be used
        # to learn which addresses have bought ads.
        return {
            "status": "success",
            "message": "If campaigns exist for this email, an access link has been sent.",
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"[marketing] Request access failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _review_state(row) -> str:
    if row["status"] == "rejected":
        return "rejected"
    if row["approved_at"]:
        return "approved"
    return "awaiting_review" if row["status"] == "paid" else "not_paid"


# --- admin: review and delivery follow-up -------------------------------------


@router.get("/marketing/admin/campaigns")
async def admin_list_campaigns(view: str = "review", authorized: bool = Depends(verify_admin)):
    """review: paid, waiting for approval. underdelivered: grace period over with
    impressions short (refund candidates). all: everything, newest first."""
    where = {
        "review": "status = 'paid' AND approved_at IS NULL",
        "underdelivered": f"""status = 'paid' AND approved_at IS NOT NULL
            AND CURRENT_DATE > end_date + {AD_DELIVERY_GRACE_DAYS}
            AND impressions_delivered < target_impressions""",
        "all": "TRUE",
    }.get(view)
    if where is None:
        raise HTTPException(status_code=400, detail="view must be review, underdelivered or all")
    rows = await db.async_execute(
        f"""
        SELECT id, buyer_name, buyer_email, slot_id, target_impressions, impressions_delivered,
               clicks, start_date, end_date, status, approved_at, review_note, image_url, target_url,
               created_at
        FROM advertising_campaigns
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT 200
        """  # nosec B608 - only module constants are interpolated; values are bound params
    )
    campaigns = []
    for r in rows or []:
        paid_cents = _amount_cents(r["slot_id"], r["target_impressions"])
        shortfall = max(0, r["target_impressions"] - r["impressions_delivered"])
        campaigns.append(
            {
                "id": r["id"],
                "buyer_name": r["buyer_name"],
                "buyer_email": r["buyer_email"],
                "slot_id": r["slot_id"],
                "status": r["status"],
                "review": _review_state(r),
                "target_impressions": r["target_impressions"],
                "impressions_delivered": r["impressions_delivered"],
                "clicks": r["clicks"],
                "start_date": r["start_date"].isoformat(),
                "end_date": r["end_date"].isoformat(),
                "image_url": r["image_url"],
                "target_url": r["target_url"],
                "paid_eur": paid_cents / 100,
                # Pro-rata refund for impressions never delivered.
                "refund_due_eur": round(paid_cents * shortfall / r["target_impressions"] / 100, 2),
            }
        )
    return {"status": "success", "view": view, "campaigns": campaigns}


@router.post("/marketing/admin/campaigns/{campaign_id}/approve")
async def admin_approve_campaign(
    campaign_id: str,
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    row = await db.async_execute_one(
        """
        UPDATE advertising_campaigns SET approved_at = NOW(), review_note = NULL
        WHERE id = %s AND status = 'paid' AND approved_at IS NULL
        RETURNING id
        """,
        (campaign_id,),
    )
    if not row:
        raise HTTPException(status_code=409, detail="Campaign is not paid and awaiting review")
    log.info(f"[marketing] Ad campaign {campaign_id} approved.")
    return {"status": "success", "campaign_id": campaign_id, "review": "approved"}


@router.post("/marketing/admin/campaigns/{campaign_id}/reject")
async def admin_reject_campaign(
    campaign_id: str,
    reason: str = Form(...),
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Reject a paid campaign before it serves and refund it in full."""
    row = await db.async_execute_one(
        """
        SELECT stripe_payment_intent FROM advertising_campaigns
        WHERE id = %s AND status = 'paid' AND approved_at IS NULL
        """,
        (campaign_id,),
    )
    if not row:
        raise HTTPException(status_code=409, detail="Campaign is not paid and awaiting review")
    refunded = False
    if STRIPE_API_KEY and row["stripe_payment_intent"]:
        try:
            stripe.Refund.create(
                payment_intent=row["stripe_payment_intent"],
                idempotency_key=f"ad-reject-{campaign_id}",
            )
            refunded = True
        except Exception as refund_err:
            log.error(f"[marketing] Refund for rejected campaign {campaign_id} failed: {refund_err}")
            raise HTTPException(status_code=502, detail="Refund failed; campaign left awaiting review")
    await db.async_execute(
        "UPDATE advertising_campaigns SET status = 'rejected', review_note = %s WHERE id = %s",
        (reason.strip()[:500], campaign_id),
        fetch=False,
    )
    log.info(f"[marketing] Ad campaign {campaign_id} rejected (refunded={refunded}).")
    return {"status": "success", "campaign_id": campaign_id, "review": "rejected", "refunded": refunded}
