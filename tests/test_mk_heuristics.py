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
    assert (
        find_or_create_cluster(
            None,
            "Владата соопшти мерки за економијата",
            recent,
            category="Економија",
            topic="вести",
        )
        == "story-1"
    )


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
    assert (
        find_or_create_cluster(
            None,
            "Македонија победи во европската лига во одбојка",
            recent,
            category="Спорт",
            topic="спорт",
        )
        != "story-1"
    )


def _recent(cluster_id, title, topic="Politika"):
    return {
        "cluster_id": cluster_id,
        "title": title,
        "category": "Makedonija",
        "topic": topic,
        "created_at": datetime.datetime.now(),
    }


def test_same_event_headlines_merge_across_wording():
    # Regression: the same Vučić resignation event was split into three clusters
    # because semantically identical headlines scored ~0.27-0.53 on title overlap
    # alone (below the old 0.52 merge gate). The shared named entity ("Вучиќ")
    # must anchor them into one cluster.
    recent = [
        _recent(
            "vucic-1",
            "Вучиќ поднесе оставка и помилува 49 лица",
        )
    ]
    for headline in (
        "По 14 години власт Вучиќ си поднесе оставка – ќе се бори за премиер на изборите идниот месец",
        "Александар Вучиќ поднесе оставка",
        "ВУЧИЌ СЕ ОТКАЖА ОД ФУНКЦИЈАТА, НО НЕ И ОД ПОЛИТИКАТА",
    ):
        assert (
            find_or_create_cluster(
                None,
                headline,
                recent,
                category="Makedonija",
                topic="Politika",
                source="Telma",
            )
            == "vucic-1"
        ), headline


def test_unrelated_same_topic_headlines_stay_separate():
    # Different stories that merely share the broad topic bucket must not merge,
    # even at the lower thresholds.
    recent = [
        _recent("quake", "ЗЕМЈОТРЕС ЈА ЗАТРЕСЕ ПРЕСПА Потресот почувствуван"),
        _recent("hospital", "Пронајден човечки леш во околина на јавната болница"),
    ]
    assert (
        find_or_create_cluster(
            None,
            "Променливо облачно време со сончеви периоди и температура",
            recent,
            category="Makedonija",
            topic="vesti",
            source="Vecer",
        )
        != "quake"
    )
    assert (
        find_or_create_cluster(
            None,
            "Приведен 21 возач поради безобѕирно возење",
            recent,
            category="Makedonija",
            topic="vesti",
            source="Sitel",
        )
        != "hospital"
    )
