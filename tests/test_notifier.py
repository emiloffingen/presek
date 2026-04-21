import pytest
from unittest.mock import patch, MagicMock
from notifier import BreakingNewsNotifier


class TestBreakingNewsNotifier:
    def test_init_defaults(self):
        n = BreakingNewsNotifier(topic="test-topic")
        assert n.topic == "test-topic"
        assert n.threshold == 3

    def test_init_custom_threshold(self):
        n = BreakingNewsNotifier(topic="t", threshold=5)
        assert n.threshold == 5

    @patch('notifier.redis_client')
    def test_dedup_prevents_double_notify(self, mock_redis):
        """Same cluster_id should only be notified once based on Redis state."""
        n = BreakingNewsNotifier(topic="test")
        # First call: not in Redis
        mock_redis.get.return_value = None
        
        with patch.object(n, 'send_ntfy') as mock_ntfy:
            n.notify("Breaking news!", 5, "cluster-1")
            
            # Second call: now in Redis
            mock_redis.get.return_value = b"1"
            n.notify("Breaking news!", 5, "cluster-1")  # duplicate

            assert mock_ntfy.call_count == 1
            mock_redis.set.assert_called()

    @patch('notifier.redis_client')
    def test_different_clusters_both_notified(self, mock_redis):
        n = BreakingNewsNotifier(topic="test")
        mock_redis.get.return_value = None
        with patch.object(n, 'send_ntfy') as mock_ntfy:
            n.notify("News A", 3, "cluster-1")
            n.notify("News B", 4, "cluster-2")
            assert mock_ntfy.call_count == 2

    def test_notify_message_format(self):
        n = BreakingNewsNotifier(topic="test")
        with patch.object(n, '_is_notified', return_value=False):
            with patch.object(n, '_mark_as_notified'):
                with patch.object(n, 'send_ntfy') as mock_ntfy:
                    n.notify("Важна вест", 5, "c1")
                    call_args = mock_ntfy.call_args
                    # The message argument for send_ntfy is the second positional argument
                    # or the 'message' keyword argument.
                    msg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get('message')
                    assert "Важна вест" in msg
                    assert "5 извори" in msg

    @patch('httpx.Client.post')
    def test_send_ntfy_error_handled(self, mock_post):
        """Network errors should be caught, not raised."""
        import httpx
        mock_post.side_effect = httpx.RequestError("Connection refused", request=MagicMock())
        n = BreakingNewsNotifier(topic="test")
        # Should not raise
        n.send_ntfy("Title", "Message", "c1")
