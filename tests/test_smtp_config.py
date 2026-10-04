from tasks.utils import _resolve_from_address, send_email


def test_from_address_prefers_explicit(monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "Presek <briefing@presek.mk>")
    assert _resolve_from_address("resend") == "Presek <briefing@presek.mk>"


def test_from_address_never_bare_resend(monkeypatch):
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    assert _resolve_from_address("resend") == "Presek <briefing@presek.mk>"
    assert _resolve_from_address("mailer@presek.mk") == "mailer@presek.mk"


def test_send_email_without_config_returns_false(monkeypatch):
    for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "EMAIL_FROM"):
        monkeypatch.delenv(key, raising=False)
    assert send_email("<p>x</p>", "subject", "", "", "someone@example.com") is False
