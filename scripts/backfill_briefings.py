#!/usr/bin/env python3
"""Backfill daily briefings for specific dates (SR + MK)."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks.delivery.briefing import generate_daily_brief_task
from tasks.utils import redis_client


def _clear_lock(lang: str, date_str: str) -> None:
    key = f"lock:daily_brief:{lang}:{date_str}"
    try:
        redis_client.delete(key)
        print(f"   cleared lock {key}")
    except Exception as exc:
        print(f"   warning: could not clear lock {key}: {exc}")


def backfill_dates(dates: list[str], langs: list[str], queue: bool) -> None:
    for date_str in dates:
        for lang in langs:
            print(f"\n=== {date_str} ({lang}) ===")
            _clear_lock(lang, date_str)
            if queue:
                result = generate_daily_brief_task.apply_async(
                    kwargs={"retry_attempt": 0, "lang": lang, "briefing_date": date_str},
                    queue="delivery",
                )
                print(f"   queued task {result.id}")
            else:
                generate_daily_brief_task(retry_attempt=0, lang=lang, briefing_date=date_str)
                print("   completed inline")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill daily briefings for one or more dates.")
    parser.add_argument("dates", nargs="+", help="Dates to backfill (YYYY-MM-DD)")
    parser.add_argument("--lang", choices=("sr", "mk", "both"), default="both")
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Run synchronously in this process instead of queueing to Celery",
    )
    args = parser.parse_args()

    langs = ["sr", "mk"] if args.lang == "both" else [args.lang]
    backfill_dates(args.dates, langs, queue=not args.inline)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
