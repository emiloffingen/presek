"""Tests for Cloudflare KV storage operations."""
import pytest
import json
from unittest.mock import patch, MagicMock


class TestPutKV:
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', '')
    def test_no_credentials_returns_false(self):
        from cloudflare_kv import put_kv
        assert put_kv("key", "value") is False

    @patch('cloudflare_kv.CLOUDFLARE_KV_NAMESPACE_ID', '')
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', 'token')
    def test_no_namespace_returns_false(self):
        from cloudflare_kv import put_kv
        assert put_kv("key", "value") is False

    @patch('cloudflare_kv.CLOUDFLARE_KV_NAMESPACE_ID', 'ns-id')
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', 'token')
    @patch('cloudflare_kv.urllib.request.urlopen')
    def test_successful_put(self, mock_urlopen):
        from cloudflare_kv import put_kv
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"success": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert put_kv("key", "value") is True

    @patch('cloudflare_kv.CLOUDFLARE_KV_NAMESPACE_ID', 'ns-id')
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', 'token')
    @patch('cloudflare_kv.urllib.request.urlopen')
    def test_put_json_value(self, mock_urlopen):
        from cloudflare_kv import put_kv
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"success": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert put_kv("key", {"data": 123}) is True

    @patch('cloudflare_kv.CLOUDFLARE_KV_NAMESPACE_ID', 'ns-id')
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', 'token')
    @patch('cloudflare_kv.urllib.request.urlopen')
    def test_put_network_error(self, mock_urlopen):
        from cloudflare_kv import put_kv
        mock_urlopen.side_effect = Exception("Timeout")
        assert put_kv("key", "val") is False


class TestGetKV:
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', '')
    def test_no_credentials(self):
        from cloudflare_kv import get_kv
        assert get_kv("key") is None

    @patch('cloudflare_kv.CLOUDFLARE_KV_NAMESPACE_ID', 'ns-id')
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', 'token')
    @patch('cloudflare_kv.urllib.request.urlopen')
    def test_successful_get_json(self, mock_urlopen):
        from cloudflare_kv import get_kv
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": "hello"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = get_kv("key", is_json=True)
        assert result == {"data": "hello"}

    @patch('cloudflare_kv.CLOUDFLARE_KV_NAMESPACE_ID', 'ns-id')
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', 'token')
    @patch('cloudflare_kv.urllib.request.urlopen')
    def test_successful_get_string(self, mock_urlopen):
        from cloudflare_kv import get_kv
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"plain text"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = get_kv("key", is_json=False)
        assert result == "plain text"

    @patch('cloudflare_kv.CLOUDFLARE_KV_NAMESPACE_ID', 'ns-id')
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', 'token')
    @patch('cloudflare_kv.urllib.request.urlopen')
    def test_404_returns_none(self, mock_urlopen):
        import urllib.error
        from cloudflare_kv import get_kv
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://test", code=404, msg="Not Found", hdrs={}, fp=MagicMock()
        )
        assert get_kv("missing-key") is None

    @patch('cloudflare_kv.CLOUDFLARE_KV_NAMESPACE_ID', 'ns-id')
    @patch('cloudflare_kv.CLOUDFLARE_API_TOKEN', 'token')
    @patch('cloudflare_kv.urllib.request.urlopen')
    def test_network_error(self, mock_urlopen):
        from cloudflare_kv import get_kv
        mock_urlopen.side_effect = Exception("Timeout")
        assert get_kv("key") is None
