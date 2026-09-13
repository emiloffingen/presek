from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

# Top-level import binds collection-era modules once. Deferred (function-level)
# imports would re-execute app modules mid-session against whatever happens
# to be in sys.modules then, creating duplicate class objects that escape
# narrow pytest.raises checks (see _raise_http_error note in routes/security).
from routes.stats import get_archive


@pytest.mark.anyio
async def test_archive_invalid_date_returns_400_not_500():
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
