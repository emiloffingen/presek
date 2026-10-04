"""Daily digest: send the morning briefing to plain email newsletter subscribers.

Restored from the MK-only stub. Generation/personalization live in
tasks/delivery/morning_brief.py; this is the plain-subscriber delivery entry
point used by the scheduled `send_daily_digest_task`.
"""

from tasks.utils import log


def send_digest(days: int = 1) -> int:
    from tasks.delivery.morning_brief import send_morning_brief_to
    from tasks.delivery.subscribers import _load_newsletter_subscribers

    targets = _load_newsletter_subscribers()
    if not targets:
        log.info("[digest] no newsletter subscribers")
        return 0
    delivered = send_morning_brief_to(targets)
    log.info(f"[digest] morning briefing delivered to {len(delivered)}/{len(targets)} subscribers")
    return len(delivered)
