import datetime
from unittest.mock import patch, MagicMock
from clustering import mk_stem, text_to_vector, get_cosine, find_or_create_cluster, _title_phrase_overlap, _topic_bridge_allowed
from collections import Counter

# db_manager is imported inside find_or_create_cluster as `from database import db_manager`,
# so we must patch the source attribute on the database module.
_mock_db = MagicMock()
_mock_db.get_cluster_entities.return_value = {}
_DB_PATCH = 'database.db_manager'

def test_mk_stem():
    assert mk_stem("владата") == "влад"
    assert mk_stem("влада") == "влада"  # No suffix
    assert mk_stem("учењето") == "учење"  # length constraint skips 'ењето', strips 'то'
    assert mk_stem("краток") == "краток"  # no matching suffix

def test_text_to_vector():
    # Stopwords should be removed
    vec = text_to_vector("Ова е тест за владата")
    assert "ова" not in vec
    assert "е" not in vec
    assert "за" not in vec
    # Stemming should be applied
    assert vec["тест"] == 1
    assert vec["влад"] == 1

def test_get_cosine():
    vec1 = Counter({"влада": 1, "тест": 1})
    vec2 = Counter({"влада": 1, "уче": 1})
    vec3 = Counter({"нешто": 1, "сосема": 1, "различно": 1})
    
    # Cosine similarity of identical vectors should be 1.0
    assert abs(get_cosine(vec1, vec1) - 1.0) < 0.001
    
    # Cosine similarity of completely disjoint vectors should be 0.0
    assert get_cosine(vec1, vec3) == 0.0
    
    # Cosine similarity of partially overlapping vectors
    score = get_cosine(vec1, vec2)
    assert 0.0 < score < 1.0

def test_title_phrase_overlap_prefers_shared_bigram_structure():
    close = _title_phrase_overlap(
        "Владата усвои пакет мерки за економија",
        "Нов пакет мерки за економија усвои владата"
    )
    far = _title_phrase_overlap(
        "Владата усвои пакет мерки за економија",
        "Фудбалски натпревар во Лига Шампиони"
    )
    assert close > far


def test_topic_bridge_is_more_permissive_for_fresh_followups_than_old_ones():
    shared = {"Кочани"}
    assert _topic_bridge_allowed("Политика", "Вести", "Македонија", "Македонија", 0.0, 0.55, shared, 4.0) is True
    assert _topic_bridge_allowed("Политика", "Вести", "Македонија", "Македонија", 0.0, 0.55, shared, 30.0) is False

@patch(_DB_PATCH, _mock_db)
def test_find_or_create_cluster():
    recent_articles = [
        {"cluster_id": "c1", "title": "Владата донесе нова мерка за економијата"},
        {"cluster_id": "c1", "title": "Нова мерка на владата за економија"},
        {"cluster_id": "c2", "title": "Спортски настан во Скопје"}
    ]

    # Should match cluster 1 (use very similar words to pass threshold 0.35)
    title1 = "Владата донесе мерка за економијата"
    cid1 = find_or_create_cluster(MagicMock(), title1, recent_articles)
    assert cid1 == "c1"

    # Should create new cluster
    title2 = "Временска прогноза за утре"
    cid2 = find_or_create_cluster(MagicMock(), title2, recent_articles)
    assert cid2 != "c1"
    assert cid2 != "c2"

@patch(_DB_PATCH, _mock_db)
def test_max_cluster_size():
    # Mocking a full cluster
    recent_articles = [{"cluster_id": "c1", "title": "Владата донесе нова мерка за економијата"}] * 30
    title1 = "Мерки на владата за економија"
    cid1 = find_or_create_cluster(MagicMock(), title1, recent_articles)
    assert cid1 != "c1" # Should not join full cluster


def test_empty_title_creates_new_cluster():
    """Empty or very short title should create a new cluster."""
    recent = [{"cluster_id": "c1", "title": "Владата донесе мерка"}]
    cid = find_or_create_cluster(MagicMock(), "", recent)
    assert cid != "c1"

def test_no_recent_articles():
    """With no recent articles, should always create new cluster."""
    cid = find_or_create_cluster(MagicMock(), "Нова важна вест", [])
    assert len(cid) == 8  # uuid[:8]

@patch(_DB_PATCH, _mock_db)
def test_completely_different_topic():
    """Completely unrelated titles should not cluster together."""
    recent = [
        {"cluster_id": "c1", "title": "Владата донесе нова мерка за економијата"},
    ]
    cid = find_or_create_cluster(MagicMock(), "Фудбалски натпревар во Лига Шампиони", recent)
    assert cid != "c1"

def test_mk_stem_short_words_unchanged():
    """Words shorter than 5 chars should not be stemmed."""
    assert mk_stem("мир") == "мир"
    assert mk_stem("зема") == "зема"
    assert mk_stem("а") == "а"

def test_text_to_vector_empty():
    vec = text_to_vector("")
    assert len(vec) == 0

def test_text_to_vector_all_stopwords():
    vec = text_to_vector("и на во од со за")
    assert len(vec) == 0

def test_get_cosine_empty_vectors():
    assert get_cosine(Counter(), Counter()) == 0.0
    assert get_cosine(Counter({"a": 1}), Counter()) == 0.0

def test_get_cosine_identical():
    vec = Counter({"тест": 3, "влад": 2})
    assert abs(get_cosine(vec, vec) - 1.0) < 0.001

@patch(_DB_PATCH, _mock_db)
def test_cluster_age_decay():
    """Older cluster representatives should be harder to match (higher threshold)."""
    import datetime
    old_time = datetime.datetime.now() - datetime.timedelta(hours=48)
    recent_time = datetime.datetime.now() - datetime.timedelta(minutes=5)

    title = "Владата донесе мерка за економијата"

    recent_articles = [
        {"cluster_id": "c-old", "title": "Владата донесе нова мерка за економијата", "created_at": old_time},
    ]
    fresh_articles = [
        {"cluster_id": "c-new", "title": "Владата донесе нова мерка за економијата", "created_at": recent_time},
    ]

    cid_old = find_or_create_cluster(MagicMock(), title, recent_articles)
    cid_new = find_or_create_cluster(MagicMock(), title, fresh_articles)

    # Fresh cluster should be matched, old cluster may not due to age penalty
    assert cid_new == "c-new"


@patch(_DB_PATCH, _mock_db)
def test_phrase_overlap_helps_short_variants_join_same_cluster():
    recent_articles = [
        {"cluster_id": "c1", "title": "Пакет мерки за економија од Владата", "created_at": datetime.datetime.now()},
        {"cluster_id": "c2", "title": "Фудбалски натпревар во Скопје", "created_at": datetime.datetime.now()},
    ]

    cid = find_or_create_cluster(MagicMock(), "Владата со пакет мерки за економија", recent_articles)
    assert cid == "c1"


@patch(_DB_PATCH, _mock_db)
def test_same_source_unrelated_followup_does_not_merge_after_time_gap():
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Денес е Упокоение на Свети Методиј Солунски",
            "created_at": datetime.datetime.now() - datetime.timedelta(hours=23),
            "source": "Skopje Info",
            "category": "Македонија",
            "topic": "Вести",
        }
    ]

    cid = find_or_create_cluster(
        MagicMock(),
        "Пишува „Скопски Херој“: Главен град без ноќен живот – каде исчезна урбаното Скопје?",
        recent_articles,
        category="Македонија",
        source="Skopje Info",
        topic="Вести",
    )

    assert cid != "c1"


@patch(_DB_PATCH, _mock_db)
def test_topic_bridge_allows_same_story_followup_when_entities_and_title_overlap_are_strong():
    _mock_db.get_cluster_entities.return_value = {"c1": {"Кочани", "Обвинителство"}}
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Обвинителството отвори истрага за пожарот во Кочани",
            "created_at": datetime.datetime.now(),
            "source": "МИА",
            "category": "Македонија",
            "topic": "Вести",
        }
    ]

    cid = find_or_create_cluster(
        MagicMock(),
        "Кочани: Обвинителството бара нови докази во истрагата за пожарот",
        recent_articles,
        category="Македонија",
        source="Телма",
        topic="Политика",
    )

    assert cid == "c1"


@patch(_DB_PATCH, _mock_db)
def test_topic_bridge_does_not_merge_same_category_story_without_shared_entities_or_overlap():
    _mock_db.get_cluster_entities.return_value = {"c1": {"Кочани", "Обвинителство"}}
    recent_articles = [
        {
            "cluster_id": "c1",
            "title": "Обвинителството отвори истрага за пожарот во Кочани",
            "created_at": datetime.datetime.now(),
            "source": "МИА",
            "category": "Македонија",
            "topic": "Вести",
        }
    ]

    cid = find_or_create_cluster(
        MagicMock(),
        "Владата отвора нов конкурс за директори на училишта",
        recent_articles,
        category="Македонија",
        source="Сител",
        topic="Политика",
    )

    assert cid != "c1"
