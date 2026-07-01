from unittest.mock import AsyncMock, patch

import pytest

from core.cross_lingual import get_cross_lingual_counterparts


@pytest.mark.asyncio
async def test_get_cross_lingual_counterparts_maps_rows():
    with patch(
        "core.cross_lingual.db.async_execute",
        new=AsyncMock(
            return_value=[
                {
                    "cluster_id": "abc123",
                    "lang": "mk",
                    "synthetic_headline": "Наслов",
                    "storyline_title": "Storyline",
                    "relevance_score": 0.9,
                }
            ]
        ),
    ):
        rows = await get_cross_lingual_counterparts("sr_cluster", "sr")
    assert len(rows) == 1
    assert rows[0]["cluster_id"] == "abc123"
    assert rows[0]["lang"] == "mk"
