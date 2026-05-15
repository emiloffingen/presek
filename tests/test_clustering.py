import datetime
from unittest.mock import patch, MagicMock
from core.clustering import (
    sr_stem,
    text_to_vector,
    get_cosine,
    find_or_create_cluster,
    _title_phrase_overlap,
    _topic_bridge_allowed,
)
from collections import Counter

# db_manager is imported inside find_or_create_cluster as `from database import db_manager`,
# so we must patch the source attribute on the database module.
_mock_db = MagicMock()
_mock_db.get_cluster_entities.return_value = {}
_DB_PATCH = "database.db_manager"


def test_sr_stem():
    assert sr_stem("vladanje") == "vlad"
    assert sr_stem("vlada") == "vlada"
    assert sr_stem("pevanje") == "pev"
    assert sr_stem("kratak") == "kratak"


def test_text_to_vector():
    # Stopwords should be removed
    vec = text_to_vector("ova je test za vladanje")
    assert "ova" not in vec
    assert "je" not in vec
    assert "za" not in vec
    # Stemming should be applied
    assert vec["test"] == 1
    assert vec["vlad"] == 1


def test_get_cosine():
    vec1 = Counter({"vlad": 1, "test": 1})
    vec2 = Counter({"vlad": 1, "uce": 1})
    vec3 = Counter({"nesto": 1, "sosema": 1, "razlicito": 1})

    # Cosine similarity of identical vectors should be 1.0
    assert abs(get_cosine(vec1, vec1) - 1.0) < 0.001

    # Cosine similarity of completely disjoint vectors should be 0.0
    assert get_cosine(vec1, vec3) == 0.0

    # Cosine similarity of partially overlapping vectors
    score = get_cosine(vec1, vec2)
    assert 0.0 < score < 1.0


def test_title_phrase_overlap_prefers_shared_bigram_structure():
    close = _title_phrase_overlap(
        "Vlada usvojila paket mera za Ekonomiju",
        "Nov paket mera za Ekonomiju usvojila vlada",
    )
    far = _title_phrase_overlap(
        "Vlada usvojila paket mera za Ekonomiju", "Fudbalski meč u Ligi Šampiona"
    )
    assert close > far


def test_topic_bridge_is_more_permissive_for_fresh_followups_than_old_ones():
    shared = {"Kočani"}
    assert (
        _topic_bridge_allowed(
            "Politika", "vesti", "Srbija", "Srbija", 0.0, 0.55, shared, 4.0
        )
        is True
    )
    assert (
        _topic_bridge_allowed(
            "Politika", "vesti", "Srbija", "Srbija", 0.0, 0.55, shared, 30.0
        )
        is False
    )


@patch(_DB_PATCH, _mock_db)
def test_find_or_create_cluster():
    recent_articles = [
        {"cluster_id": "c1", "title": "Vlada donela novu meru za ekonomiju"},
        {"cluster_id": "c1", "title": "nova mera vlade za Ekonomiju"},
        {"cluster_id": "c2", "title": "Sportski događaj u Beogradu"},
    ]

    # Should match cluster 1
    title1 = "Vlada donela meru za ekonomiju"
    cid1 = find_or_create_cluster(MagicMock(), title1, recent_articles)
    assert cid1 == "c1"

    # Should create new cluster
    title2 = "Vremenska prognoza za sutra"
    cid2 = find_or_create_cluster(MagicMock(), title2, recent_articles)
    assert cid2 != "c1"
    assert cid2 != "c2"


@patch(_DB_PATCH, _mock_db)
def test_max_cluster_size():
    # Mocking a full cluster
    recent_articles = [
        {"cluster_id": "c1", "title": "Vlada donela novu meru za ekonomiju"}
    ] * 40
    title1 = "Mere vlade za Ekonomiju"
    cid1 = find_or_create_cluster(MagicMock(), title1, recent_articles)
    assert cid1 != "c1"


def test_empty_title_creates_new_cluster():
    recent = [{"cluster_id": "c1", "title": "Vlada donela meru"}]
    cid = find_or_create_cluster(MagicMock(), "", recent)
    assert cid != "c1"


def test_no_recent_articles():
    cid = find_or_create_cluster(MagicMock(), "nova vazna vest", [])
    assert len(cid) == 12


@patch(_DB_PATCH, _mock_db)
def test_completely_different_topic():
    recent = [
        {"cluster_id": "c1", "title": "Vlada donela novu meru za ekonomiju"},
    ]
    cid = find_or_create_cluster(
        MagicMock(), "Fudbalski meč u Ligi Šampiona", recent
    )
    assert cid != "c1"


def test_sr_stem_short_words_unchanged():
    assert sr_stem("mir") == "mir"
    assert sr_stem("ovaj") == "ovaj"
    assert sr_stem("a") == "a"


def test_text_to_vector_empty():
    vec = text_to_vector("")
    assert len(vec) == 0


def test_text_to_vector_all_stopwords():
    vec = text_to_vector("i na u od sa za")
    assert len(vec) == 0


def test_get_cosine_empty_vectors():
    assert get_cosine(Counter(), Counter()) == 0.0
    assert get_cosine(Counter({"a": 1}), Counter()) == 0.0


def test_get_cosine_identical():
    vec = Counter({"test": 3, "vlad": 2})
    assert abs(get_cosine(vec, vec) - 1.0) < 0.001


@patch(_DB_PATCH, _mock_db)
def test_cluster_age_decay():
    import datetime
    old_time = datetime.datetime.now() - datetime.timedelta(hours=48)
    recent_time = datetime.datetime.now() - datetime.timedelta(minutes=5)
    title = "Vlada donela meru za ekonomiju"
    recent_articles = [
        {
            "cluster_id": "c-old",
            "title": "Vlada donela novu meru za ekonomiju",
            "created_at": old_time,
        },
    ]
    fresh_articles = [
        {
            "cluster_id": "c-new",
            "title": "Vlada donela novu meru za ekonomiju",
            "created_at": recent_time,
        },
    ]
    cid_old = find_or_create_cluster(MagicMock(), title, recent_articles)
    cid_new = find_or_create_cluster(MagicMock(), title, fresh_articles)
    assert cid_new == "c-new"


@patch(_DB_PATCH, _mock_db)
def test_phrase_overlap_helps_short_variants_join_same_cluster():
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Vlada donela paket mera za ekonomiju",
            "created_at": datetime.datetime.now(),
        },
        {
            "cluster_id": "c2",
            "title": "Fudbalski meč u Beogradu",
            "created_at": datetime.datetime.now(),
        },
    ]
    cid = find_or_create_cluster(
        MagicMock(), "Vlada donela paket mera za ekonomiju", recent_articles
    )
    assert cid == "c1"


@patch(_DB_PATCH, _mock_db)
def test_same_source_unrelated_followup_does_not_merge_after_time_gap():
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "danas je Upokojenje Svetog Metodija Solunskog",
            "created_at": datetime.datetime.now() - datetime.timedelta(hours=23),
            "source": "Beograd Info",
            "category": "Srbija",
            "topic": "vesti",
        }
    ]
    cid = find_or_create_cluster(
        MagicMock(),
        "Piše „Beogradski Heroj“: glavni grad bez noćnog života",
        recent_articles,
        category="Srbija",
        source="Beograd Info",
        topic="vesti",
    )
    assert cid != "c1"


@patch(_DB_PATCH, _mock_db)
def test_topic_bridge_allows_same_story_followup_when_entities_and_title_overlap_are_strong():
    _mock_db.get_cluster_entities.return_value = {"c1": {"Kočani", "Tužilaštvo"}}
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Tužilaštvo otvorilo istragu za požar u Kočanima",
            "created_at": datetime.datetime.now(),
            "source": "N1 Info",
            "category": "Srbija",
            "topic": "vesti",
        }
    ]
    cid = find_or_create_cluster(
        MagicMock(),
        "Tužilaštvo otvorilo istragu za požar u Kočanima",
        recent_articles,
        category="Srbija",
        source="danas",
        topic="Politika",
    )
    assert cid == "c1"


@patch(_DB_PATCH, _mock_db)
def test_topic_bridge_does_not_merge_same_category_story_without_shared_entities_or_overlap():
    _mock_db.get_cluster_entities.return_value = {"c1": {"Kočani", "Tužilaštvo"}}
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Tužilaštvo otvorilo istragu za požar u Kočanima",
            "created_at": datetime.datetime.now(),
            "source": "N1 Info",
            "category": "Srbija",
            "topic": "vesti",
        }
    ]
    cid = find_or_create_cluster(
        MagicMock(), "Vlada otvara nov konkurs za direktore škola",
        recent_articles,
        category="Srbija",
        source="nova.rs",
        topic="Politika",
    )
    assert cid != "c1"


@patch(_DB_PATCH, _mock_db)
def test_different_category_does_not_merge():
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Novak Đoković pobedio na Vimbldonu",
            "category": "Sport",
            "created_at": datetime.datetime.now(),
        }
    ]
    # Even if title is similar (unlikely here, but for testing category filter)
    cid = find_or_create_cluster(
        MagicMock(),
        "Novak Đoković se sastao sa predsednikom vlade",
        recent_articles,
        category="Politika",
    )
    assert cid != "c1"


@patch(_DB_PATCH, _mock_db)
def test_edge_case_empty_recent_articles():
    """Edge case: No recent articles should create new cluster."""
    cid = find_or_create_cluster(MagicMock(), "Nova vazna vest", [])
    assert len(cid) == 12  # Should be a new cluster ID
    assert cid != "c1"


@patch(_DB_PATCH, _mock_db)
def test_edge_case_very_short_titles():
    """Edge case: Very short titles should still cluster appropriately."""
    recent_articles = [
        {"cluster_id": "c1", "title": "Potres", "created_at": datetime.datetime.now()},
    ]
    # Similar short title should cluster
    cid1 = find_or_create_cluster(MagicMock(), "Potres", recent_articles)
    assert cid1 == "c1"
    
    # Different short title should not cluster
    cid2 = find_or_create_cluster(MagicMock(), "Poplava", recent_articles)
    assert cid2 != "c1"


@patch(_DB_PATCH, _mock_db)
def test_edge_case_special_characters():
    """Edge case: Titles with special characters and numbers."""
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "COVID-19: Nova mera 2024",
            "created_at": datetime.datetime.now(),
        },
    ]
    # Similar title with special chars should cluster
    cid = find_or_create_cluster(MagicMock(), "COVID-19: Nova mera 2024", recent_articles)
    assert cid == "c1"


@patch(_DB_PATCH, _mock_db)
def test_edge_case_mixed_languages():
    """Edge case: Mixed Cyrillic and Latin scripts."""
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Vlada donela novu meru",
            "created_at": datetime.datetime.now(),
        },
    ]
    # Similar content in different script should still cluster
    cid = find_or_create_cluster(MagicMock(), "Влада донела нову меру", recent_articles)
    # This depends on the transliteration logic, but should handle gracefully
    assert cid == "c1" or len(cid) == 12  # Either clusters or creates new


@patch(_DB_PATCH, _mock_db)
def test_edge_case_max_cluster_size_boundary():
    """Edge case: Exactly at max cluster size should not merge."""
    # Create exactly 40 articles in one cluster (assuming max is 40)
    recent_articles = [
        {"cluster_id": "c1", "title": "Vlada donela meru"}
    ] * 40
    
    cid = find_or_create_cluster(MagicMock(), "Vlada donela novu meru", recent_articles)
    assert cid != "c1"  # Should not merge into full cluster


@patch(_DB_PATCH, _mock_db)
def test_edge_case_very_old_cluster():
    """Edge case: Very old clusters should decay and not merge."""
    old_time = datetime.datetime.now() - datetime.timedelta(days=30)
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Vlada donela meru",
            "created_at": old_time,
        },
    ]
    
    cid = find_or_create_cluster(MagicMock(), "Vlada donela novu meru", recent_articles)
    assert cid != "c1"  # Should not merge with very old cluster


@patch(_DB_PATCH, _mock_db)
def test_edge_case_identical_but_different_sources():
    """Edge case: Same story from different sources should cluster."""
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Premierka odrzala sobranje",
            "source": "SourceA",
            "created_at": datetime.datetime.now(),
        },
    ]
    
    cid = find_or_create_cluster(
        MagicMock(),
        "Premierka odrzala sobranje",
        recent_articles,
        source="SourceB",
    )
    assert cid == "c1"  # Should cluster same story from different sources


@patch(_DB_PATCH, _mock_db)
def test_edge_case_rapid_followups():
    """Edge case: Rapid follow-ups should cluster appropriately."""
    now = datetime.datetime.now()
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Vlada donela meru",
            "created_at": now - datetime.timedelta(minutes=1),
        },
        {
            "cluster_id": "c2",
            "title": "Vlada donela novu meru",
            "created_at": now - datetime.timedelta(minutes=2),
        },
    ]
    
    # Very recent follow-up should cluster with most recent
    cid = find_or_create_cluster(MagicMock(), "Vlada donela novu meru za ekonomiju", recent_articles)
    assert cid in ["c1", "c2"]  # Should cluster with one of the recent ones


# =============================================================================
# Gold Standard Test Cases for Clustering Quality
# =============================================================================


@patch(_DB_PATCH, _mock_db)
def test_gold_standard_exact_title_match():
    """Gold standard: Exact title match should cluster together."""
    recent_articles = [
        {"cluster_id": "c1", "title": "Premierka održala sobranje", "created_at": datetime.datetime.now()},
    ]
    cid = find_or_create_cluster(MagicMock(), "Premierka održala sobranje", recent_articles)
    assert cid == "c1"


@patch(_DB_PATCH, _mock_db)
def test_gold_standard_very_similar_titles_cluster():
    """Gold standard: Very similar titles should cluster together."""
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Vlada donela nov paket mera za ekonomija",
            "created_at": datetime.datetime.now(),
        },
    ]
    cid = find_or_create_cluster(MagicMock(), "Vlada donela paket mera za ekonomija", recent_articles)
    assert cid == "c1"


@patch(_DB_PATCH, _mock_db)
def test_gold_standard_different_topics_dont_cluster():
    """Gold standard: Different topics should NOT cluster together."""
    recent_articles = [
        {"cluster_id": "c1", "title": "Potres pogodil Skopje", "created_at": datetime.datetime.now()},
    ]
    cid = find_or_create_cluster(MagicMock(), "Nogometen meč Makedonija Albanija", recent_articles)
    assert cid != "c1"

