import pytest
from unittest.mock import MagicMock, patch

from tasks.delivery.briefing import notify_daily_briefing_ready_task


def test_notify_daily_briefing_ready_skips_when_dedupe_locked():
    fake_redis = MagicMock()
    fake_redis.set.return_value = False

    with patch("tasks.delivery.briefing.redis_client", fake_redis), patch(
        "tasks.delivery.briefing._load_active_delivery_rows",
        return_value=[{"morning_briefing": True, "locale": "sr", "target": "topic", "channel": "ntfy"}],
    ), patch("tasks.delivery.briefing._send_ntfy_message") as send_ntfy:
        notify_daily_briefing_ready_task("sr")
        send_ntfy.assert_not_called()


def test_notify_daily_briefing_ready_sends_locale_subscribers():
    fake_redis = MagicMock()
    fake_redis.set.return_value = True

    rows = [
        {"morning_briefing": True, "locale": "sr", "target": "topic-sr", "channel": "ntfy"},
        {"morning_briefing": True, "locale": "mk", "target": "topic-mk", "channel": "ntfy"},
        {"morning_briefing": False, "locale": "sr", "target": "ignored", "channel": "ntfy"},
    ]

    with patch("tasks.delivery.briefing.redis_client", fake_redis), patch(
        "tasks.delivery.briefing._load_active_delivery_rows",
        return_value=rows,
    ), patch("tasks.delivery.briefing._send_ntfy_message", return_value=True) as send_ntfy:
        notify_daily_briefing_ready_task("sr")

    assert send_ntfy.call_count == 1
    assert send_ntfy.call_args.args[0] == "topic-sr"
