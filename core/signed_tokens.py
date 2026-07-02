"""HMAC-signed tokens for newsletter unsubscribe and delivery tracking."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import quote

NEWSLETTER_UNSUBSCRIBE_TTL = 90 * 24 * 3600
DELIVERY_TRACK_TTL = 30 * 24 * 3600
ALLOWED_DELIVERY_EVENT_TYPES = frozenset({"click", "open", "view"})


def _secret() -> bytes:
    key = os.environ.get("SECRET_KEY", "")
    if not key:
        raise RuntimeError("SECRET_KEY is required for signed tokens")
    return key.encode("utf-8")


def _sign(message: str) -> str:
    return hmac.new(_secret(), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _encode_signed(payload: str, ttl: int) -> str:
    exp = int(time.time()) + ttl
    message = f"{payload}:{exp}"
    sig = _sign(message)
    raw = f"{message}:{sig}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_signed(token: str) -> str | None:
    if not token:
        return None
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + padding).encode("ascii")).decode(
            "utf-8"
        )
        canonical = (
            base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
        )
        if not hmac.compare_digest(token, canonical):
            return None
        payload, exp_str, sig = raw.rsplit(":", 2)
        exp = int(exp_str)
        if exp < int(time.time()):
            return None
        message = f"{payload}:{exp}"
        if not hmac.compare_digest(_sign(message), sig):
            return None
        return payload
    except Exception:
        return None


def build_newsletter_unsubscribe_token(email: str, locale: str) -> str:
    clean_email = email.strip().lower()
    clean_locale = "mk" if str(locale or "sr").strip().lower() == "mk" else "sr"
    return _encode_signed(
        f"unsub|{clean_email}|{clean_locale}", NEWSLETTER_UNSUBSCRIBE_TTL
    )


def parse_newsletter_unsubscribe_token(token: str) -> tuple[str, str] | None:
    payload = _decode_signed(token)
    if not payload or not payload.startswith("unsub|"):
        return None
    _, email, locale = payload.split("|", 2)
    if locale not in {"sr", "mk"} or not email:
        return None
    return email, locale


def build_newsletter_unsubscribe_url(base_url: str, email: str, locale: str) -> str:
    token = build_newsletter_unsubscribe_token(email, locale)
    lang = "mk" if str(locale or "sr").strip().lower() == "mk" else "sr"
    return f"{base_url.rstrip('/')}/api/newsletter/unsubscribe?token={quote(token)}&lang={lang}"


def build_delivery_track_token(event_id: int, event_type: str, redirect: str) -> str:
    clean_type = str(event_type or "click").strip().lower()
    if clean_type not in ALLOWED_DELIVERY_EVENT_TYPES:
        clean_type = "click"
    clean_redirect = str(redirect or "/briefing").strip()
    if not clean_redirect.startswith("/"):
        clean_redirect = "/briefing"
    return _encode_signed(
        f"track|{int(event_id)}|{clean_type}|{clean_redirect}", DELIVERY_TRACK_TTL
    )


def parse_delivery_track_token(token: str) -> tuple[int, str, str] | None:
    payload = _decode_signed(token)
    if not payload or not payload.startswith("track|"):
        return None
    _, event_id_str, event_type, redirect = payload.split("|", 3)
    if event_type not in ALLOWED_DELIVERY_EVENT_TYPES:
        return None
    try:
        event_id = int(event_id_str)
    except ValueError:
        return None
    if event_id <= 0:
        return None
    return event_id, event_type, redirect
