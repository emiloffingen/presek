import pytest
from unittest.mock import patch
from core.topic_discovery import StoryDiscoveryEngine

@pytest.fixture
def discovery_engine():
    return StoryDiscoveryEngine()

@patch("core.topic_discovery.db")
def test_update_storyline_centroid(mock_db, discovery_engine):
    # Test that _update_storyline_centroid executes the correct SQL
    discovery_engine._update_storyline_centroid(123)
    
    mock_db.execute.assert_called()
    args, kwargs = mock_db.execute.call_args
    assert "UPDATE storylines_v2" in args[0]
    assert "AVG(m.centroid)" in args[0]
    assert args[1] == (123, 123)

@patch("core.topic_discovery.db")
def test_run_discovery_uses_centroid(mock_db, discovery_engine):
    # Test that run_discovery uses cluster_metadata.centroid
    mock_db.execute.return_value = []
    discovery_engine.run_discovery(48)
    
    mock_db.execute.assert_called()
    args, kwargs = mock_db.execute.call_args
    assert "m.centroid as avg_embedding" in args[0]
    assert "JOIN cluster_metadata m" in args[0]

from nlp.local_analyst import LocalAnalyst

@patch("core.topic_discovery.db")
@patch.object(LocalAnalyst, "analyze")
def test_create_new_storyline_with_centroid(mock_analyze, mock_db, discovery_engine):
    mock_analyze.return_value = "New Story Title"
    cluster = {
        "cluster_id": "test_cid",
        "titles": ["Title 1"],
        "avg_embedding": [0.1] * 384
    }
    
    discovery_engine._create_new_storyline(cluster)
    
    # Check that INSERT into storylines_v2 includes centroid
    insert_call = [call for call in mock_db.execute.call_args_list if "INSERT INTO storylines_v2" in call[0][0]][0]
    assert "centroid" in insert_call[0][0]
    assert cluster["avg_embedding"] in insert_call[0][1]
