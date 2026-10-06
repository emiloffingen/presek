"""
Test feed functionality.
"""

import asyncio
from contextlib import ExitStack
from unittest.mock import patch

import routes.home as home_routes
import routes.intelligence as intelligence_routes


async def _empty_news_data(*args, **kwargs):
    return {"clusters": [], "global_clusters": []}


async def _empty_list(*args, **kwargs):
    return []


async def _empty_stats(*args, **kwargs):
    return {}


async def _empty_briefing(*args, **kwargs):
    return None


def _patch_home_dependencies(**overrides):
    """Patch every dependency that get_home fans out to.

    get_home gathers these concurrently (routes/home.py:get_home). Any one left
    unpatched falls through to the real implementation, which queries Postgres and
    blocks the test on the connection pool timeout.
    """
    deps = {
        "cached_response": patch.object(home_routes, "cached_response", return_value=None),
        "set_cache": patch.object(home_routes, "set_cache", return_value=None),
        "fetch_news_data": patch.object(home_routes, "fetch_news_data", side_effect=_empty_news_data),
        "get_trending_route": patch.object(home_routes, "get_trending_route", side_effect=_empty_list),
        "get_stats_summary": patch.object(home_routes, "get_stats_summary", side_effect=_empty_stats),
        "get_top_entities": patch.object(home_routes, "get_top_entities", side_effect=_empty_list),
        "fetch_synthesis_hero_candidates": patch.object(
            home_routes, "fetch_synthesis_hero_candidates", side_effect=_empty_list
        ),
        "get_latest_briefing": patch.object(intelligence_routes, "get_latest_briefing", side_effect=_empty_briefing),
    }
    deps.update(overrides)
    return deps


def test_get_home_returns_dict():
    """Test that get_home returns a dictionary."""
    with ExitStack() as stack:
        for patcher in _patch_home_dependencies().values():
            stack.enter_context(patcher)
        result = asyncio.run(home_routes.get_home("sr"))

    # Should return a dictionary
    assert isinstance(result, dict)

    # Should have expected keys
    assert "developing" in result
    assert "excluded_cluster_ids" in result


def test_get_home_language_support():
    """Test that get_home supports different languages."""
    with ExitStack() as stack:
        for patcher in _patch_home_dependencies().values():
            stack.enter_context(patcher)

        # Test Serbian
        result_sr = asyncio.run(home_routes.get_home("sr"))
        assert isinstance(result_sr, dict)

        # Test Macedonian
        result_mk = asyncio.run(home_routes.get_home("mk"))
        assert isinstance(result_mk, dict)


def test_get_home_error_handling():
    """Test that get_home handles database errors gracefully."""

    async def fail_news_data(*args, **kwargs):
        raise Exception("DB error")

    with ExitStack() as stack:
        deps = _patch_home_dependencies(
            fetch_news_data=patch.object(home_routes, "fetch_news_data", side_effect=fail_news_data),
        )
        for patcher in deps.values():
            stack.enter_context(patcher)
        result = asyncio.run(home_routes.get_home("sr"))

    # Should still return a dict even on error
    assert isinstance(result, dict)
    assert result["status"] == "error"
