import pytest
import datetime
import json
from unittest.mock import AsyncMock, patch
from core.topic_discovery import StoryDiscoveryEngine
from tasks.intelligence import refine_knowledge_graph_sentiment_task

@pytest.mark.anyio
@patch("routes.news.db")
async def test_cluster_detail_works_without_llama_cpp(mock_db):
    from routes.news import get_cluster_detail

    mock_db.async_execute = AsyncMock(return_value=[
        {
            "id": "art_1",
            "title": "СДСМ предлага нови награди",
            "description": "Прва реченица за настанот. Втора реченица.",
            "source": "Фронтлајн.мк",
            "created_at": datetime.datetime(2026, 6, 12, 12, 0),
            "category": "Makedonija",
            "country": "MK",
            "source_signal": {"trust_level": 0.9},
        }
    ])
    mock_db.async_execute_one = AsyncMock(return_value=None)
    mock_db.async_get_synthesis_ids = AsyncMock(return_value=[])

    with patch("nlp.local_analyst._import_llama_cpp", return_value=(None, None)), \
         patch("routes.news._is_publicly_displayable_article", return_value=True), \
         patch("routes.news.annotate_cluster_articles", side_effect=lambda x, **k: x), \
         patch("routes.news.cached_response", return_value=None):
        response = await get_cluster_detail("abcdef0123456789abcdef0123456789", lang="mk")
        assert response["status"] == "success"
        assert response["data"]["timeline"][0]["title"]


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


@patch("tasks.intelligence.get_celery_queue_depth", return_value=0)
@patch("tasks.intelligence.db")
@patch("nlp.analyze_sentiment_locally", return_value=1.5)
def test_refine_knowledge_graph_sentiment_task_updates_db(mock_analyze, mock_db, _mock_queue_depth):
    # Test that refine_knowledge_graph_sentiment_task refines sentiment in the database
    mock_db.execute.return_value = [
        {
            "cluster_id": "c1",
            "titles": ["Sjajan napredak i pobeda"],
            "desc": "Izuzetno dobar razvoj dogadjaja na svim poljima."
        }
    ]

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


@pytest.mark.anyio
@patch("routes.news.db")
async def test_stance_vectors_and_divergence_in_cluster_detail(mock_db):
    # Verify get_cluster_detail computes stance_vectors and editorial_divergence
    from routes.news import get_cluster_detail
    
    mock_db.async_execute = AsyncMock(return_value=[
        {
            "id": "art_1",
            "title": "Odlican napredak i uspeh vlada",
            "description": "pobeda i razvoj reformi", # highly positive words
            "source": "RTS",
            "created_at": datetime.datetime(2026, 5, 26, 12, 0),
            "category": "Politika",
            "country": "RS",
            "source_signal": {"trust_level": 0.9}
        },
        {
            "id": "art_2",
            "title": "Katastrofa, haos i propast",
            "description": "loso, kriminal i neuspeh", # highly negative words
            "source": "Danas",
            "created_at": datetime.datetime(2026, 5, 26, 12, 5),
            "category": "Politika",
            "country": "RS",
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
        data = response["data"]
        
        # Verify stance_vectors has both sources and positive/negative scores
        assert "RTS" in data["stance_vectors"]
        assert "Danas" in data["stance_vectors"]
        assert data["stance_vectors"]["RTS"] > 0
        assert data["stance_vectors"]["Danas"] < 0
        
        # Divergence standard deviation should be positive
        assert data["editorial_divergence"] > 0.5


@patch("tasks.maintenance.db")
def test_maintenance_weight_decay_and_pruning(mock_db):
    # Verify that repair_knowledge_graph_task triggers weight decay and relationship pruning
    from tasks.maintenance import repair_knowledge_graph_task
    mock_db.execute.return_value = [{"name": "A", "total_mentions": 1, "sentiment_score": 0.0, "type": "ENTITY"}]
    
    repair_knowledge_graph_task()
    
    db_calls = [call[0][0] for call in mock_db.execute.call_args_list]
    decay_calls = [c for c in db_calls if "weight = weight * EXP" in c]
    prune_calls = [c for c in db_calls if "DELETE FROM knowledge_relationships WHERE weight" in c]
    
    assert len(decay_calls) > 0
    assert len(prune_calls) > 0


@patch("core.topic_discovery.db")
def test_adaptive_storyline_threshold(mock_db):
    # Verify StoryDiscoveryEngine applies adaptive thresholds based on velocity
    engine = StoryDiscoveryEngine()
    
    # 1. Existing storyline
    mock_db.execute_one.return_value = {
        "id": 999,
        "title": "Ujedinjena prica",
        "metadata": json.dumps({"lang": "sr"}),
        "distance": 0.38 # Close but exceeds standard 0.35 threshold!
    }
    mock_db.execute.return_value = [{"country": "RS"}]
    
    # Low-velocity cluster: link_threshold becomes 0.30, shouldn't merge at distance 0.38
    cluster_slow = {
        "cluster_id": "c_slow",
        "avg_embedding": [0.1] * 384,
        "velocity": 1,
        "source_count": 2,
        "titles": ["Spora vest"]
    }
    engine._process_cluster(cluster_slow)
    
    # High-velocity cluster: link_threshold becomes 0.40, SHOULD merge at distance 0.38!
    cluster_fast = {
        "cluster_id": "c_fast",
        "avg_embedding": [0.1] * 384,
        "velocity": 4, # High velocity!
        "source_count": 3,
        "titles": ["Brza vest"]
    }
    engine._process_cluster(cluster_fast)
    
    # Verify that the high-velocity cluster was successfully inserted into storyline clusters
    insert_calls = [call for call in mock_db.execute.call_args_list if "INSERT INTO storyline_clusters_v2" in call[0][0]]
    assert len(insert_calls) == 1
    assert insert_calls[0][0][1] == (999, "c_fast", 0.62) # 1 - 0.38 distance
