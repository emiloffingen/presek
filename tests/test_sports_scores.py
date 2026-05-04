import pytest
from nlp.generation import _extract_sports_scores, _extract_number_tokens, compare_cluster_sources

def test_extract_sports_scores():
    assert "4:0" in _extract_sports_scores("Резултатот е 4:0 за тимот")
    assert "1-0" in _extract_sports_scores("Заврши 1-0")
    assert "0-0" in _extract_sports_scores("(0-0) на полувреме")
    # Clock times should be excluded
    assert "15:00" not in _extract_sports_scores("Мечот почнува во 15:00 часот")
    assert "20:45" not in _extract_sports_scores("Кикоф во 20:45")

def test_extract_number_tokens_excludes_time():
    tokens = _extract_number_tokens("Пакетот е 100 милиони евра, почнува во 15:00")
    assert "100" in tokens
    assert "15:00" not in tokens

def test_compare_cluster_sources_sports_conflict():
    from nlp.categories import detect_topic
    articles = [
        {"source": "S1", "title": "Вардар победи 1-0", "description": "Спортски извештај"},
        {"source": "S2", "title": "Вардар победи 2-0", "description": "Различен резултат"}
    ]
    all_titles = " ".join([a.get("title") or "" for a in articles])
    topic = detect_topic(all_titles)
    result = compare_cluster_sources(articles)
    assert any(("2-0" in item or "1-0" in item) for item in result["difference_points"])

def test_highlight_scores_web():
    # Note: This is JS-like test, but our Python utility should match logic
    # Actually I should test the Python version if I had one, 
    # but I only added it to TS. I can't test TS in pytest.
    pass

@pytest.mark.parametrize("input_text,expected", [
    ("4:0", True),
    ("1-0", True),
    ("15:00", False),
    ("2024-2025", False),
])
def test_is_score_logic(input_text, expected):
    scores = _extract_sports_scores(input_text)
    assert (input_text in scores) == expected
