import datetime

from tasks.intelligence.cluster_ops import plan_cluster_merges


def _row(id_, cluster_id, title, source="Telma", topic="Politika", category="Makedonija"):
    return {
        "id": id_,
        "cluster_id": cluster_id,
        "title": title,
        "source": source,
        "topic": topic,
        "category": category,
        "created_at": datetime.datetime.now(),
    }


def test_plan_merges_same_event_split_clusters():
    rows = [
        _row(1, "canon", "Вучиќ поднесе оставка и помилува 49 лица", source="360 Stepeni"),
        _row(2, "canon", "Вучиќ поднесе оставка, пред крај помилува 49 лица", source="Sitel"),
        _row(3, "dup-a", "Александар Вучиќ поднесе оставка", source="A1on"),
        _row(4, "dup-b", "По 14 години власт Вучиќ си поднесе оставка – ќе се бори за премиер", source="Telma"),
        _row(5, "dup-c", "ВУЧИЌ СЕ ОТКАЖА ОД ФУНКЦИЈАТА, НО НЕ И ОД ПОЛИТИКАТА", source="Plusinfo"),
    ]
    plan = plan_cluster_merges(rows)
    assert len(plan) == 1
    canonical, dups, count = plan[0]
    assert canonical == "canon"
    assert set(dups) == {"dup-a", "dup-b", "dup-c"}
    assert count == 3  # duplicate clusters' article count


def test_plan_keeps_unrelated_same_topic_clusters_separate():
    rows = [
        _row(1, "quake", "ЗЕМЈОТРЕС ЈА ЗАТРЕСЕ ПРЕСПА Потресот почувствуван", topic="vesti", source="Vecer"),
        _row(2, "weather", "Променливо облачно време со сончеви периоди", topic="vesti", source="Plusinfo"),
        _row(3, "crashes", "Приведен 21 возач поради безобѕирно возење", topic="vesti", source="Sitel"),
    ]
    assert plan_cluster_merges(rows) == []


def test_plan_ignores_rows_without_cluster_or_title():
    rows = [
        _row(1, None, "Вучиќ поднесе оставка"),
        _row(2, "x", ""),
        _row(3, "canon", "Вучиќ поднесе оставка и помилува 49 лица"),
        _row(4, "dup", "Вучиќ поднесе оставка и помилува 49 лица"),
    ]
    plan = plan_cluster_merges(rows)
    assert len(plan) == 1
    assert plan[0][0] == "canon"
    assert "dup" in plan[0][1]
