"""Focused regression test for /api/news search with lang-based country inference."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = ["tests.test_api_fast"]


def test_api_news_search_lang_sr_infers_country_rs(mock_all):
    """Calling /api/news?q=...&lang=sr must map to country='RS' and return 200."""
    import routes.news as news

    with (
        patch("routes.news.cached_response", return_value=None),
        patch("routes.news.set_cache"),
        patch("core.embeddings.get_query_embedding_async", new=AsyncMock(return_value=None)),
    ):
        response = asyncio.run(news.get_news(q="Tramp", page_size=12, lang="sr"))

    # Success path returns a dict via the (fake) FastAPI route wrapper.
    # Error path returns a JSONResponse with status_code=500.
    status_code = getattr(response, "status_code", 200)
    data = response.content if hasattr(response, "content") else response

    assert status_code == 200, f"Expected 200, got {status_code}: {data}"
    assert data["status"] == "success"
    assert data["page"] == 0
    assert data["page_size"] == 12

    # The non-embedding fallback must be used in this test so we can assert
    # the country parameter that is passed to the search layer.
    assert mock_all["db"].async_search_articles.called is True
    call_kwargs = mock_all["db"].async_search_articles.call_args.kwargs
    assert call_kwargs.get("country") == "RS", (
        f"Expected country='RS' when lang='sr', got {call_kwargs.get('country')!r}"
    )
