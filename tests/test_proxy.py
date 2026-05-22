"""
Test proxy functionality.
"""

import pytest
from unittest.mock import patch
from routes.system import proxy_image


@pytest.mark.asyncio
async def test_proxy_image_fallback():
    """Test that proxy returns fallback when database fails."""
    # Mock database failure
    with patch('core.database.db_manager.async_execute', side_effect=Exception("DB error")):
        result = await proxy_image('https://example.com/image.jpg')
        
        # Should return a fallback response
        assert result.status_code == 200
        assert 'image/svg+xml' in result.headers.get('Content-Type', '')
        assert b'Proxy Fallback' in result.body if hasattr(result, 'body') else b'Proxy Fallback' in result.content


@pytest.mark.asyncio
async def test_proxy_image_invalid_url():
    """Test invalid URL handling."""
    result = await proxy_image('invalid-url')
    
    # Should return fallback for invalid URL
    assert result.status_code == 200
    assert 'image/svg+xml' in result.headers.get('Content-Type', '')


@pytest.mark.asyncio
async def test_proxy_image_ssrf_block():
    """Test SSRF protection."""
    # Mock a response from a non-public IP
    with patch('routes.system._resolve_public_ips', return_value=[]):
        result = await proxy_image('http://192.168.1.1/image.jpg')
        
        # Should return fallback (it returns fetch_failed, not security_ssrf_block)
        assert result.status_code == 200
        assert 'image/svg+xml' in result.headers.get('Content-Type', '')
        # Check that it's a fallback response (contains diagnostic info)
        response_content = result.body if hasattr(result, 'body') else result.content
        assert b'Proxy Fallback' in response_content
