"""
Test feed functionality.
"""

import asyncio
from unittest.mock import patch

import routes.home as home_routes


async def _empty_news_data(*args, **kwargs):
    return {"clusters": [], "global_clusters": []}


async def _empty_list(*args, **kwargs):
    return []


async def _empty_stats(*args, **kwargs):
    return {}


def _patch_home_dependencies():
    return (
        patch.object(home_routes, 'cached_response', return_value=None),
        patch.object(home_routes, 'set_cache', return_value=None),
        patch.object(home_routes, 'fetch_news_data', side_effect=_empty_news_data),
        patch.object(home_routes, 'get_trending_route', side_effect=_empty_list),
        patch.object(home_routes, 'get_stats_summary', side_effect=_empty_stats),
    )


def test_get_home_returns_dict():
    """Test that get_home returns a dictionary."""
    with _patch_home_dependencies()[0], _patch_home_dependencies()[1], _patch_home_dependencies()[2], \
         _patch_home_dependencies()[3], _patch_home_dependencies()[4]:
        result = asyncio.run(home_routes.get_home('sr'))
        
        # Should return a dictionary
        assert isinstance(result, dict)
        
        # Should have expected keys
        assert 'developing' in result
        assert 'excluded_cluster_ids' in result


def test_get_home_language_support():
    """Test that get_home supports different languages."""
    with _patch_home_dependencies()[0], _patch_home_dependencies()[1], _patch_home_dependencies()[2], \
         _patch_home_dependencies()[3], _patch_home_dependencies()[4]:
        # Test Serbian
        result_sr = asyncio.run(home_routes.get_home('sr'))
        assert isinstance(result_sr, dict)
        
        # Test Macedonian
        result_mk = asyncio.run(home_routes.get_home('mk'))
        assert isinstance(result_mk, dict)


def test_get_home_error_handling():
    """Test that get_home handles database errors gracefully."""
    async def fail_news_data(*args, **kwargs):
        raise Exception("DB error")

    with patch.object(home_routes, 'cached_response', return_value=None), \
         patch.object(home_routes, 'fetch_news_data', side_effect=fail_news_data), \
         patch.object(home_routes, 'get_trending_route', side_effect=_empty_list), \
         patch.object(home_routes, 'get_stats_summary', side_effect=_empty_stats):
        result = asyncio.run(home_routes.get_home('sr'))
        
        # Should still return a dict even on error
        assert isinstance(result, dict)
        assert result["status"] == "error"
