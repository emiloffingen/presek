import pytest
from clustering import mk_stem, text_to_vector, get_cosine, find_or_create_cluster
from collections import Counter

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

def test_find_or_create_cluster():
    recent_articles = [
        {"cluster_id": "c1", "title": "Владата донесе нова мерка за економијата"},
        {"cluster_id": "c1", "title": "Нова мерка на владата за економија"},
        {"cluster_id": "c2", "title": "Спортски настан во Скопје"}
    ]
    
    # Should match cluster 1 (use very similar words to pass threshold 0.35)
    title1 = "Владата донесе мерка за економијата"
    cid1 = find_or_create_cluster(title1, recent_articles)
    assert cid1 == "c1"
    
    # Should create new cluster
    title2 = "Временска прогноза за утре"
    cid2 = find_or_create_cluster(title2, recent_articles)
    assert cid2 != "c1"
    assert cid2 != "c2"

def test_max_cluster_size():
    # Mocking a full cluster
    recent_articles = [{"cluster_id": "c1", "title": "Владата донесе нова мерка за економијата"}] * 30
    title1 = "Мерки на владата за економија"
    cid1 = find_or_create_cluster(title1, recent_articles)
    assert cid1 != "c1" # Should not join full cluster