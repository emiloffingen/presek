"""Fast production smoke checks for the Macedonian deployment."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.database import db_manager as db


BASE_URL = os.environ.get("SMOKE_BASE_URL", "https://presek.mk").rstrip("/")


def get(path: str) -> tuple[int, bytes]:
    try:
        with urlopen(Request(f"{BASE_URL}{path}", headers={"User-Agent": "presek-smoke/1.0"}), timeout=20) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()
    except URLError as exc:
        raise RuntimeError(f"request failed for {path}: {exc}") from exc


def main() -> int:
    failures: list[str] = []

    status, body = get("/")
    if status != 200:
        failures.append(f"homepage returned HTTP {status}")
    if b"<html lang=\"mk\"" not in body:
        failures.append("homepage is not marked as Macedonian")
    if b"data-testid=\"article-card\"" not in body:
        failures.append("homepage contains no article cards")

    status, body = get("/api/health")
    if status != 200:
        failures.append(f"health returned HTTP {status}")
    else:
        health = json.loads(body)
        if health.get("status") != "healthy":
            failures.append(f"health status is {health.get('status')}")
        if not health.get("database", {}).get("ok"):
            failures.append("database health is not ok")
        if not health.get("redis", {}).get("ok"):
            failures.append("redis health is not ok")

    status, body = get("/api/news?page_size=1&lang=mk")
    if status != 200 or json.loads(body).get("status") != "success":
        failures.append("Macedonian news API is not healthy")

    status, body = get("/marketing")
    if status not in (200, 302) or (status == 200 and "Рекламирањето е привремено паузирано".encode("utf-8") not in body):
        failures.append("Stripe-disabled marketing state is not visible")

    required_tables = {"feed_sources", "cluster_summaries", "advertising_campaigns"}
    tables = {
        row["table_name"]
        for row in db.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (list(required_tables),),
        )
    }
    missing = required_tables - tables
    if missing:
        failures.append(f"missing runtime tables: {', '.join(sorted(missing))}")

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PASS: homepage, API, Neon, Redis, news feed, and Stripe-disabled state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Test marker: verifies Termux auto-deploy restart path.
