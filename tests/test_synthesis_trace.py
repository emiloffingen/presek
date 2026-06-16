from unittest.mock import AsyncMock, patch

import pytest

from core.synthesis_trace import build_cluster_synthesis_trace


@pytest.mark.asyncio
async def test_build_cluster_synthesis_trace_shapes_payload():
    fake_articles = [
        {
            "id": 1,
            "title": "Test",
            "source": "Blic",
            "created_at": None,
            "ingested_at": None,
            "category": "Politika",
            "topic": "Politika",
            "country": "RS",
        }
    ]
    fake_summary = [
        {
            "lang": "sr",
            "summary": "Sažetak",
            "synthetic_headline": "Naslov",
            "synthetic_standfirst": "",
            "generated_article": "Clanak",
            "generation_provider": "local",
            "generation_model": "gemma",
            "quality_score": 0.82,
            "fallback_reason": None,
            "created_at": None,
            "pulse_score": 55,
            "pluralism_score": 20,
        }
    ]

    with patch("core.synthesis_trace.db.async_execute", new_callable=AsyncMock) as mock_execute:
        mock_execute.side_effect = [fake_articles, fake_summary, []]
        with patch("core.synthesis_trace.list_stuck_fast_synthesis_cluster_ids", return_value=[]):
            trace = await build_cluster_synthesis_trace("cluster-a", lang="sr")

    assert trace["cluster_id"] == "cluster-a"
    assert trace["article_count"] == 1
    assert trace["languages"][0]["generation_provider"] == "local"
    assert "recommended_actions" in trace
