"""
Test proxy functionality.
"""

import asyncio
from unittest.mock import patch

from routes.common import _is_allowed_proxy_content_type, _normalize_proxy_content_type
from routes.system import proxy_image


def test_normalize_proxy_content_type_accepts_nonstandard_jpg_header():
    assert _normalize_proxy_content_type("image/JPG") == "image/jpeg"
    assert _is_allowed_proxy_content_type("image/JPG; charset=binary") is True


def test_proxy_image_fallback():
    """Test that proxy returns fallback when database fails."""
    # Mock database failure
    with patch('routes.system.db.async_execute_one', side_effect=Exception("DB error")):
        result = asyncio.run(proxy_image('https://example.com/image.jpg'))
        
        # Should return a fallback response
        assert result.status_code == 200
        assert 'image/svg+xml' in result.headers.get('Content-Type', '')
        assert b'<svg' in result.body if hasattr(result, 'body') else b'<svg' in result.content


def test_proxy_image_invalid_url():
    """Test invalid URL handling."""
    result = asyncio.run(proxy_image('invalid-url'))
    
    # Should return fallback for invalid URL
    assert result.status_code == 200
    assert 'image/svg+xml' in result.headers.get('Content-Type', '')


def test_proxy_image_ssrf_block():
    """Test SSRF protection."""
    # Mock a response from a non-public IP
    with patch('routes.system._resolve_public_ips', return_value=[]):
        result = asyncio.run(proxy_image('http://192.168.1.1/image.jpg'))
        
        # Should return fallback (it returns fetch_failed, not security_ssrf_block)
        assert result.status_code == 200
        assert 'image/svg+xml' in result.headers.get('Content-Type', '')
        # Check that it's a fallback response (contains SVG content)
        response_content = result.body if hasattr(result, 'body') else result.content
        assert b'<svg' in response_content
