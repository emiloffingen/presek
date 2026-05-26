import pytest
import datetime
import json
from unittest.mock import AsyncMock, patch, MagicMock
from core.topic_discovery import StoryDiscoveryEngine
from tasks.intelligence import refine_knowledge_graph_sentiment_task

@pytest.mark.anyio
@patch("routes.news.db")
async def test_timeline_consolidation_merges_duplicates(mock_db):
    # Test that get_jaccard_similarity and de-duplication correctly merge similar articles in timeline
    from routes.news import get_cluster_detail
    
    # We mock async methods as AsyncMock
    # Some articles have highly similar titles to simulate duplicate reports
    mock_db.async_execute = AsyncMock(return_value=[
        {
            "id": "art_1",
            "title": "Vlada usvojila novi predlog zakona o radu",
            "description": "Prva recenica. Druga recenica.",
            "source": "RTS",
            "created_at": datetime.datetime(2026, 5, 26, 12, 0),
            "category": "Politika",
            "country": "RS",
            "source_signal": {"trust_level": 0.9}
        },
        {
            "id": "art_2",
            "title": "Vlada Srbije usvojila novi predlog zakona o radu",
            "description": "Prva recenica. Druga recenica.",
            "source": "Danas",
            "created_at": datetime.datetime(2026, 5, 26, 12, 5),
            "category": "Politika",
            "country": "RS",
            "source_signal": {"trust_level": 0.8}
        },
        {
            "id": "art_3",
            "title": "Novi incident na granici i rast tenzija",
            "description": "Potpuno drugacija vest. Druga recenica.",
            "source": "MIA",
            "created_at": datetime.datetime(2026, 5, 26, 14, 0),
            "category": "Balkan",
            "country": "MK",
            "source_signal": {"trust_level": 0.8}
        }
    ])
    mock_db.async_execute_one = AsyncMock(return_value=None)
    mock_db.async_get_synthesis_ids = AsyncMock(return_value=[])
    
    with patch("routes.news._is_publicly_displayable_article", return_value=True), \
         patch("routes.news.annotate_cluster_articles", side_effect=lambda x, **k: x), \
         patch("routes.news.cached_response", return_value=None):
        
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


@patch("tasks.intelligence.db")
@patch("nlp.local_analyst.LocalAnalyst.analyze")
def test_refine_knowledge_graph_sentiment_task_updates_db(mock_analyze, mock_db, monkeypatch):
    # Test that refine_knowledge_graph_sentiment_task refines sentiment in the database
    monkeypatch.setenv("LOCAL_MODEL_PATH", "/path/to/local/model")
    mock_db.execute.return_value = [
        {
            "cluster_id": "c1",
            "titles": ["Sjajan napredak i pobeda"],
            "desc": "Izuzetno dobar razvoj dogadjaja na svim poljima."
        }
    ]
    mock_analyze.return_value = "1.5" # Positive sentiment from mock local LLM
    
    with patch("core.entities.extract_entities", return_value=[{"name": "Vlada", "type": "ORG"}]):
        refine_knowledge_graph_sentiment_task()
        
        # Assert that UPDATE knowledge_entities was called to refine the sentiment score
        db_calls = [call[0][0] for call in mock_db.execute.call_args_list]
        update_call = [c for c in db_calls if "UPDATE knowledge_entities" in c]
        assert len(update_call) > 0
        assert "SET sentiment_score =" in update_call[0]


@patch("core.topic_discovery.db")
def test_cross_lingual_storyline_detection_updates_metadata(mock_db):
    # Test that StoryDiscoveryEngine._process_cluster marks a storyline as cross-lingual if languages differ
    engine = StoryDiscoveryEngine()
    
    # 1. Existing storyline in Serbian
    mock_db.execute_one.return_value = {
        "id": 999,
        "title": "Postojeca srpska prica",
        "metadata": json.dumps({"lang": "sr"}),
        "distance": 0.1 # Very close vector distance
    }
    
    # 2. Influx cluster in Macedonian
    mock_db.execute.return_value = [{"country": "MK"}]
    
    cluster = {
        "cluster_id": "cluster_mk_123",
        "avg_embedding": [0.1] * 384,
        "velocity": 5,
        "source_count": 4,
        "titles": ["Nova makedonska vest"]
    }
    
    engine._process_cluster(cluster)
    
    # Check that metadata was updated with is_cross_lingual and both languages
    update_metadata_calls = [call for call in mock_db.execute.call_args_list if "UPDATE storylines_v2 SET metadata" in call[0][0]]
    assert len(update_metadata_calls) == 1
    
    passed_metadata = json.loads(update_metadata_calls[0][0][1][0])
    assert passed_metadata["is_cross_lingual"] is True
    assert "sr" in passed_metadata["languages"]
    assert "mk" in passed_metadata["languages"]
