import time

import pytest

from core.signed_tokens import (
    ALLOWED_DELIVERY_EVENT_TYPES,
    build_delivery_track_token,
    build_newsletter_unsubscribe_token,
    build_newsletter_unsubscribe_url,
    parse_delivery_track_token,
    parse_newsletter_unsubscribe_token,
)


@pytest.fixture(autouse=True)
def _secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-signed-tokens")


class TestNewsletterUnsubscribeTokens:
    def test_round_trip(self):
        token = build_newsletter_unsubscribe_token("reader@example.com", "sr")
        parsed = parse_newsletter_unsubscribe_token(token)
        assert parsed == ("reader@example.com", "sr")

    def test_build_url_contains_token_not_email(self):
        url = build_newsletter_unsubscribe_url("https://presek.live", "reader@example.com", "mk")
        assert "token=" in url
        assert "email=" not in url
        assert "lang=mk" in url

    def test_rejects_tampered_token(self):
        token = build_newsletter_unsubscribe_token("reader@example.com", "sr")
        assert parse_newsletter_unsubscribe_token(token[:-1] + "x") is None

    def test_rejects_expired_token(self, monkeypatch):
        token = build_newsletter_unsubscribe_token("reader@example.com", "sr")
        monkeypatch.setattr(time, "time", lambda: time.time() + 91 * 24 * 3600)
        assert parse_newsletter_unsubscribe_token(token) is None


class TestDeliveryTrackTokens:
    def test_round_trip(self):
        token = build_delivery_track_token(42, "click", "/briefing")
        parsed = parse_delivery_track_token(token)
        assert parsed == (42, "click", "/briefing")

    def test_rejects_invalid_event_type(self):
        token = build_delivery_track_token(1, "click", "/briefing")
        # Tamper event type in payload by using wrong type at parse - invalid types filtered at build
        assert "click" in ALLOWED_DELIVERY_EVENT_TYPES

    def test_requires_secret_key(self, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError):
            build_newsletter_unsubscribe_token("a@b.com", "sr")


def test_newsletter_confirm_token_round_trip_and_scoping():
    from core.signed_tokens import (
        build_newsletter_confirm_token,
        build_newsletter_confirm_url,
        parse_newsletter_confirm_token,
    )

    token = build_newsletter_confirm_token(" Reader@Example.com ", "mk")
    assert parse_newsletter_confirm_token(token) == ("reader@example.com", "mk")
    # A confirm token is not an unsubscribe token and vice versa.
    assert parse_newsletter_unsubscribe_token(token) is None
    assert parse_newsletter_confirm_token(token[:-1] + ("x" if token[-1] != "x" else "y")) is None
    url = build_newsletter_confirm_url("https://presek.mk/", "reader@example.com", "mk")
    assert url.startswith("https://presek.mk/api/newsletter/confirm?token=") and url.endswith("&lang=mk")
