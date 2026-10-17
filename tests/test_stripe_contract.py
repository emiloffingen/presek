"""Contract tests for the parts of stripe-python that routes/marketing.py relies on.

They run the real SDK against a local fake Stripe API, so an SDK upgrade that
changes the wire format, the pinned API version, the webhook verification
or the object model fails here instead of in a customer's checkout.
"""

import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl

import pytest
import stripe

import routes.marketing as marketing


@pytest.fixture()
def fake_stripe(monkeypatch):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _respond(self):
            length = int(self.headers.get("content-length") or 0)
            seen.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "version": self.headers.get("Stripe-Version"),
                    "idempotency": self.headers.get("Idempotency-Key"),
                    "params": dict(parse_qsl(self.rfile.read(length).decode())),
                }
            )
            if "/refunds" in self.path:
                body = {"id": "re_1", "object": "refund", "status": "succeeded"}
            else:
                body = {
                    "id": "cs_test_1",
                    "object": "checkout.session",
                    "url": "https://checkout.stripe.com/c/pay/cs_test_1",
                }
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = _respond

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(stripe, "api_base", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(stripe, "api_key", "sk_test_contract")
    monkeypatch.setattr(stripe, "api_version", marketing.STRIPE_API_VERSION or None)
    yield seen
    server.shutdown()
    server.server_close()


def test_checkout_session_wire_format(fake_stripe):
    session = stripe.checkout.Session.create(
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": "Presek Banner Ad - Top Banner", "description": "d"},
                    "unit_amount": 9150,
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        managed_payments={"enabled": False},
        success_url="https://presek.mk/marketing?status=success&campaign_id=1",
        cancel_url="https://presek.mk/marketing?status=cancel",
        metadata={"campaign_id": "1"},
        idempotency_key="ad-checkout-1",
    )
    assert session.id == "cs_test_1"
    assert session.url.startswith("https://checkout.stripe.com/")

    req = fake_stripe[0]
    assert (req["method"], req["path"]) == ("POST", "/v1/checkout/sessions")
    assert req["version"] == marketing.STRIPE_API_VERSION  # the pin is what is sent, not the SDK default
    assert req["idempotency"] == "ad-checkout-1"
    assert req["params"]["mode"] == "payment"
    assert req["params"]["line_items[0][price_data][unit_amount]"] == "9150"
    assert req["params"]["managed_payments[enabled]"] == "false"
    assert req["params"]["metadata[campaign_id]"] == "1"
    # Dynamic payment methods: removed from Checkout in stripe-python 16, must stay unset.
    assert "payment_method_types[0]" not in req["params"]


def test_refund_wire_format(fake_stripe):
    refund = stripe.Refund.create(payment_intent="pi_1", idempotency_key="ad-reject-1")
    assert refund.status == "succeeded"
    req = fake_stripe[0]
    assert (req["method"], req["path"]) == ("POST", "/v1/refunds")
    assert req["params"] == {"payment_intent": "pi_1"}
    assert req["idempotency"] == "ad-reject-1"
    assert req["version"] == marketing.STRIPE_API_VERSION


def test_retrieved_session_is_not_a_dict(fake_stripe):
    prior = stripe.checkout.Session.retrieve("cs_test_1")
    # Regression: the idempotent-retry path used prior.get("url"), which raises
    # AttributeError on a StripeObject and sent the customer to the success page.
    with pytest.raises(AttributeError):
        prior.get("url")
    assert getattr(prior, "url", None) == "https://checkout.stripe.com/c/pay/cs_test_1"
    assert getattr(stripe.checkout.Session.construct_from({"id": "cs_x"}, "k"), "url", None) is None


def _signed(payload: bytes, secret: str, ts: int | None = None) -> str:
    ts = int(time.time()) if ts is None else ts
    digest = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def test_webhook_signature_verification():
    secret = "whsec_contract"
    payload = json.dumps(
        {"id": "evt_1", "object": "event", "type": "checkout.session.completed", "data": {"object": {"id": "cs_1"}}}
    ).encode()

    stripe.Webhook.construct_event(payload, _signed(payload, secret), secret)

    with pytest.raises(stripe.error.SignatureVerificationError):
        stripe.Webhook.construct_event(payload, _signed(payload, "whsec_other"), secret)
    with pytest.raises(stripe.error.SignatureVerificationError):
        stripe.Webhook.construct_event(payload, "garbage", secret)
    with pytest.raises(stripe.error.SignatureVerificationError):  # replay outside the tolerance window
        stripe.Webhook.construct_event(payload, _signed(payload, secret, ts=int(time.time()) - 3600), secret)
    with pytest.raises(stripe.error.SignatureVerificationError):  # tampered body
        stripe.Webhook.construct_event(payload + b" ", _signed(payload, secret), secret)
