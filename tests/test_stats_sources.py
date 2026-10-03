from unittest.mock import AsyncMock, patch

import pytest

from routes.stats import get_sources_route


def _patched(**names):
    # Patch the module get_sources_route really executes in (robust to sys.modules re-imports).
    return patch.dict(get_sources_route.__globals__, names)


@pytest.mark.anyio
async def test_sources_route_returns_bare_list_on_cache_miss():
    rows = [{"source": "Kurir", "country": "MK"}]
    mock_db = AsyncMock()
    mock_db.async_execute = AsyncMock(return_value=[])
    with _patched(
        db=mock_db,
        cached_response=lambda key, ttl=None: None,
        set_cache=lambda *a, **k: None,
        build_source_reputation_rows=lambda *a, **k: rows,
    ):
        result = await get_sources_route()

    assert result == rows


@pytest.mark.anyio
async def test_sources_route_cache_hit_and_miss_share_a_shape():
    rows = [{"source": "Kurir", "country": "MK"}]
    mock_db = AsyncMock()
    mock_db.async_execute = AsyncMock(return_value=[])
    with _patched(db=mock_db, cached_response=lambda key, ttl=None: rows):
        hit = await get_sources_route()
    with _patched(
        db=mock_db,
        cached_response=lambda key, ttl=None: None,
        set_cache=lambda *a, **k: None,
        build_source_reputation_rows=lambda *a, **k: rows,
    ):
        miss = await get_sources_route()

    assert isinstance(hit, list) and isinstance(miss, list)
