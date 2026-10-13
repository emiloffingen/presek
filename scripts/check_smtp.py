#!/usr/bin/env python3
"""Verify SMTP mail config without sending anything, and optionally send one
test message. Prints no secret values.

    set -a; . ./.env; set +a
    .venv/bin/python scripts/check_smtp.py                 # login check only
    .venv/bin/python scripts/check_smtp.py --send-to you@example.com
"""

from __future__ import annotations

import argparse
import os
import re
import smtplib
import ssl
import sys
from email.mime.text import MIMEText


def _mask(value: str) -> str:
    if not value:
        return "<missing>"
    return value if len(value) <= 4 else f"{value[:2]}…{value[-2:]}"


def _envelope_addr(value: str) -> str:
    """Bare addr-spec for the SMTP envelope (strip a display name if present)."""
    match = re.search(r"<([^>]+)>", value)
    return (match.group(1) if match else value).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Presek SMTP configuration.")
    parser.add_argument("--send-to", default="", help="address to send one test mail to")
    args = parser.parse_args()

    host = os.environ.get("SMTP_HOST", "").strip()
    try:
        port = int(os.environ.get("SMTP_PORT", "587") or 587)
    except ValueError:
        print("FAIL: SMTP_PORT is not an integer", file=sys.stderr)
        return 2
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    sender = os.environ.get("EMAIL_FROM", "").strip() or (user if "@" in user else "Presek <briefing@presek.mk>")

    print("SMTP config:")
    print(f"  host: {host or '<missing>'}")
    print(f"  port: {port}")
    print(f"  user: {_mask(user)}")
    print(f"  pass: {_mask(password)}")
    print(f"  from: {sender}")

    missing = [name for name, val in (("SMTP_HOST", host), ("SMTP_USER", user), ("SMTP_PASS", password)) if not val]
    if missing:
        print(f"\nFAIL: missing {', '.join(missing)}", file=sys.stderr)
        return 2

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(user, password)
            print("\nlogin: OK")
            if args.send_to:
                msg = MIMEText("Presek SMTP test — this is a test message.", "plain", "utf-8")
                msg["Subject"] = "Presek SMTP test"
                msg["From"] = sender
                msg["To"] = args.send_to
                server.sendmail(_envelope_addr(sender), args.send_to, msg.as_string())
                print(f"sent test mail to {args.send_to}")
    except smtplib.SMTPAuthenticationError as exc:
        print(f"\nFAIL: authentication rejected ({exc.smtp_code})", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - surface any transport error
        print(f"\nFAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
