import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch


@pytest.mark.anyio
async def test_archive_invalid_date_returns_400_not_500():
    from routes.stats import get_archive

    with pytest.raises(HTTPException) as exc:
        await get_archive(
            date="2026-06-08\" AND 1=1 --",
            q="",
            source="",
            topic="",
            lang="sr",
            page=0,
            page_size=50,
        )

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_archive_valid_date_does_not_raise_validation_error():
    from routes.stats import get_archive

    with patch("routes.stats.db") as mock_db, patch("routes.stats.cached_response", return_value=None):
        mock_db.async_execute = AsyncMock(return_value=[])
        mock_db.async_execute_one = AsyncMock(return_value={"total": 0, "source_count": 0})
        mock_db.async_get_synthesis_ids = AsyncMock(return_value=[])

        result = await get_archive(
            date="2026-06-08",
            q="",
            source="",
            topic="",
            lang="sr",
            page=0,
            page_size=50,
        )

    assert result["date"] == "2026-06-08"
    assert result["clusters"] == []
