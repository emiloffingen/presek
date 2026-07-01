from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.crawler import CrawlerService


@pytest.mark.asyncio
async def test_crawler_blocks_ssrf_peer_mismatch_without_headless_fallback():
    crawler = CrawlerService()

    mock_response = MagicMock()
    mock_response.text = "<html><body>blocked</body></html>"
    mock_response.url = "https://example.com/article"
    mock_response.raise_for_status = MagicMock()

    async def _aread():
        return None

    mock_response.aread = _aread

    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("core.crawler._resolve_public_ips", return_value={"93.184.216.34"}), patch(
        "core.crawler._peer_ip", return_value="10.0.0.1"
    ), patch("core.crawler.httpx.AsyncClient", return_value=mock_client), patch.object(
        crawler, "_extract_headless", new_callable=AsyncMock
    ) as headless_mock:
        result = await crawler.extract_all("https://example.com/article")

    assert "Security block" in result.get("error", "")
    headless_mock.assert_not_called()
