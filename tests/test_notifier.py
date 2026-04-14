import pytest
from unittest.mock import patch, MagicMock
from notifier import BreakingNewsNotifier


class TestBreakingNewsNotifier:
    def test_init_defaults(self):
        n = BreakingNewsNotifier(topic="test-topic")
        assert n.topic == "test-topic"
        assert n.threshold == 3
        assert len(n._notified) == 0

    def test_init_custom_threshold(self):
        n = BreakingNewsNotifier(topic="t", threshold=5)
        assert n.threshold == 5

    def test_dedup_prevents_double_notify(self):
        """Same cluster_id should only be notified once."""
        n = BreakingNewsNotifier(topic="test")
        with patch.object(n, 'send_ntfy') as mock_ntfy, \
             patch.object(n, 'send_telegram') as mock_tg:
            n.notify("Breaking news!", 5, "cluster-1")
            n.notify("Breaking news!", 5, "cluster-1")  # duplicate

            assert mock_ntfy.call_count == 1
            assert mock_tg.call_count == 1

    def test_different_clusters_both_notified(self):
        n = BreakingNewsNotifier(topic="test")
        with patch.object(n, 'send_ntfy'), patch.object(n, 'send_telegram'):
            n.notify("News A", 3, "cluster-1")
            n.notify("News B", 4, "cluster-2")
            assert "cluster-1" in n._notified
            assert "cluster-2" in n._notified

    def test_notify_message_format(self):
        n = BreakingNewsNotifier(topic="test")
        with patch.object(n, 'send_ntfy') as mock_ntfy, \
             patch.object(n, 'send_telegram') as mock_tg:
            n.notify("Важна вест", 5, "c1")
            call_args = mock_ntfy.call_args
            assert "Важна вест" in call_args[0][1]
            assert "5 извори" in call_args[0][1]

    @patch('httpx.Client.post')
    def test_send_ntfy_error_handled(self, mock_post):
        """Network errors should be caught, not raised."""
        import httpx
        mock_post.side_effect = httpx.RequestError("Connection refused", request=MagicMock())
        n = BreakingNewsNotifier(topic="test")
        # Should not raise
        n.send_ntfy("Title", "Message", "c1")

    def test_send_telegram_no_credentials(self):
        """Without credentials, telegram send should be a no-op."""
        n = BreakingNewsNotifier(topic="test")
        n.telegram_token = None
        n.telegram_chat_id = None
        # Should not raise
        n.send_telegram("Message", "c1")
