import datetime
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.anyio
@patch("routes.news.db")
async def test_timeline_consolidation_merges_duplicates(mock_db):
    # Test that get_jaccard_similarity and de-duplication correctly merge similar articles in timeline
    from routes.news import get_cluster_detail

    # We mock async methods as AsyncMock
    # Some articles have highly similar titles to simulate duplicate reports
    mock_db.async_execute = AsyncMock(
        return_value=[
            {
                "id": "art_1",
                "title": "Vlada usvojila novi predlog zakona o radu",
                "description": "Prva recenica. Druga recenica.",
                "source": "RTS",
                "created_at": datetime.datetime(2026, 5, 26, 12, 0),
                "category": "Politika",
                "country": "RS",
                "source_signal": {"trust_level": 0.9},
            },
            {
                "id": "art_2",
                "title": "Vlada Srbije usvojila novi predlog zakona o radu",
                "description": "Prva recenica. Druga recenica.",
                "source": "Danas",
                "created_at": datetime.datetime(2026, 5, 26, 12, 5),
                "category": "Politika",
                "country": "RS",
                "source_signal": {"trust_level": 0.8},
            },
            {
                "id": "art_3",
                "title": "Novi incident na granici i rast tenzija",
                "description": "Potpuno drugacija vest. Druga recenica.",
                "source": "MIA",
                "created_at": datetime.datetime(2026, 5, 26, 14, 0),
                "category": "Balkan",
                "country": "MK",
                "source_signal": {"trust_level": 0.8},
            },
        ]
    )
    mock_db.async_execute_one = AsyncMock(return_value=None)
    mock_db.async_get_synthesis_ids = AsyncMock(return_value=[])

    with (
        patch("routes.news._is_publicly_displayable_article", return_value=True),
        patch("routes.news.annotate_cluster_articles", side_effect=lambda x, **k: x),
        patch("routes.news.cached_response", return_value=None),
    ):
        response = await get_cluster_detail("abcdef0123456789abcdef0123456789", lang="sr")

        assert response["status"] == "success"
        timeline = response["data"]["timeline"]

        # Expected behavior:
        # art_1 and art_2 are highly similar (>0.65 similarity) and within 6 hours.
        # They must be merged into one timeline entry!
        # art_3 is different, so it should remain separate.
        # Total consolidated timeline entries = 2!
        assert len(timeline) == 2

        # Sources for the merged entry should be consolidated
        assert "RTS, Danas" in timeline[0]["source"]
        assert timeline[1]["source"] == "MIA"


@pytest.mark.anyio
@patch("routes.news.db")
async def test_cluster_detail_enqueues_jit_synthesis_when_missing(mock_db):
    from routes.news import get_cluster_detail

    mock_db.async_execute = AsyncMock(
        return_value=[
            {
                "id": "art_1",
                "title": "СДСМ предлага нови награди",
                "description": "Прва реченица за настанот.",
                "source": "Фронтлајн.мк",
                "created_at": datetime.datetime(2026, 6, 12, 12, 0),
                "category": "Makedonija",
                "country": "MK",
                "source_signal": {"trust_level": 0.9},
            },
            {
                "id": "art_2",
                "title": "СДСМ предлага нови награди 2",
                "description": "Втора реченица.",
                "source": "Канал 5",
                "created_at": datetime.datetime(2026, 6, 12, 12, 5),
                "category": "Makedonija",
                "country": "MK",
                "source_signal": {"trust_level": 0.8},
            },
        ]
    )
    mock_db.async_execute_one = AsyncMock(return_value=None)
    mock_db.async_get_synthesis_ids = AsyncMock(return_value=[])

    with (
        patch("routes.news._is_publicly_displayable_article", return_value=True),
        patch("routes.news.annotate_cluster_articles", side_effect=lambda x, **k: x),
        patch("routes.news.cached_response", return_value=None),
        patch("routes.news.set_cache") as mock_set_cache,
        patch("routes.news._maybe_enqueue_missing_synthesis") as mock_enqueue,
    ):
        response = await get_cluster_detail("13fd082e7310", lang="mk")

        assert response["status"] == "success"
        assert response["data"]["synthesis_freshness"]["reasons"] == ["missing_synthesis"]
        mock_enqueue.assert_called_once_with("13fd082e7310", response["data"]["synthesis_freshness"], 2)
        mock_set_cache.assert_called_once()
        assert mock_set_cache.call_args.kwargs["ttl"] == 120


@pytest.mark.anyio
async def test_cluster_detail_cache_hit_still_enqueues_missing_synthesis():
    from routes.news import get_cluster_detail

    cached_payload = {
        "status": "success",
        "data": {
            "articles": [
                {"source": "A"},
                {"source": "B"},
            ],
            "synthesis_freshness": {
                "reasons": ["missing_synthesis"],
                "refresh_needed": True,
                "is_stale": True,
            },
        },
    }

    with (
        patch("routes.news.cached_response", return_value=cached_payload),
        patch("routes.news._maybe_enqueue_missing_synthesis_from_cache") as mock_enqueue,
    ):
        response = await get_cluster_detail("13fd082e7310", lang="mk")

        assert response is cached_payload
        mock_enqueue.assert_called_once_with("13fd082e7310", cached_payload)
