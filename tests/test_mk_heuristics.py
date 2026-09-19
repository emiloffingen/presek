import datetime

from core.clustering import find_or_create_cluster
from core.language import detect_language


def test_language_heuristic_separates_macedonian_serbian_and_english():
    assert detect_language("Ѓорѓи ќе настапи во Скопје") == "mk"
    assert detect_language("Српска влада донела нове мере") == "sr"
    assert detect_language("The government announced new measures") == "en"


def test_title_fallback_clusters_related_headlines():
    recent = [
        {
            "cluster_id": "story-1",
            "title": "Владата соопшти нови мерки за економијата",
            "category": "Економија",
            "topic": "вести",
            "created_at": datetime.datetime.now(),
        }
    ]
    assert find_or_create_cluster(
        None,
        "Владата соопшти мерки за економијата",
        recent,
        category="Економија",
        topic="вести",
    ) == "story-1"


def test_title_fallback_keeps_unrelated_headlines_separate():
    recent = [
        {
            "cluster_id": "story-1",
            "title": "Владата соопшти нови мерки за економијата",
            "category": "Економија",
            "topic": "вести",
            "created_at": datetime.datetime.now(),
        }
    ]
    assert find_or_create_cluster(
        None,
        "Македонија победи во европската лига во одбојка",
        recent,
        category="Спорт",
        topic="спорт",
    ) != "story-1"
