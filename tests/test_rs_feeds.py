"""
Test feed functionality.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from routes.home import get_home


@pytest.mark.asyncio
async def test_get_home_returns_dict():
    """Test that get_home returns a dictionary."""
    # Mock the database to avoid real calls
    with patch('core.database.db_manager.async_execute', return_value=[]):
        result = await get_home('sr')
        
        # Should return a dictionary
        assert isinstance(result, dict)
        
        # Should have expected keys
        assert 'developing' in result
        assert 'for_you_pool' in result
        assert 'focus_entities' in result
        assert 'excluded_cluster_ids' in result


@pytest.mark.asyncio
async def test_get_home_language_support():
    """Test that get_home supports different languages."""
    with patch('core.database.db_manager.async_execute', return_value=[]):
        # Test Serbian
        result_sr = await get_home('sr')
        assert isinstance(result_sr, dict)
        
        # Test Macedonian
        result_mk = await get_home('mk')
        assert isinstance(result_mk, dict)


@pytest.mark.asyncio
async def test_get_home_error_handling():
    """Test that get_home handles database errors gracefully."""
    with patch('core.database.db_manager.async_execute', side_effect=Exception("DB error")):
        result = await get_home('sr')
        
        # Should still return a dict even on error
        assert isinstance(result, dict)
        # Should have empty lists on error
        assert result.get('developing', []) == []
        assert result.get('for_you_pool', []) == []
