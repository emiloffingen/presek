from api_helpers import normalize_perspectives, normalize_summary_text, related_questions_from_context


def test_normalize_summary_text_dedupes_and_strips_noise():
    raw = """
    Статии:
    • Главен развој: Трамп: Вторник, 20:00 часот по источно време
    • Главен развој: Трамп: Вторник, 20:00 часот по источно време
    Контекст: Американскиот претседател најави важно обраќање.
    """

    result = normalize_summary_text(raw)

    assert "Статии" not in result
    assert result.count("Главен развој") == 1
    assert "Американскиот претседател" in result


def test_normalize_perspectives_infers_angles_and_dedupes():
    raw = [
        "Повеќето извори се вртат околу царините и рокот за обраќање.",
        {"angle": "Перспектива", "content": "Повеќето извори се вртат околу царините и рокот за обраќање."},
        {"label": "Перспектива", "text": "Разликите најмногу се во акцентот и формулацијата."},
        {"angle": "", "content": "Останува нејасно дали мерките ќе стапат веднаш на сила."},
    ]

    result = normalize_perspectives(raw)

    assert len(result) == 3
    assert result[0]["angle"] == "Заедничка линија"
    assert result[1]["angle"] == "Различни акценти"
    assert result[2]["angle"] == "Што останува отворено"


def test_related_questions_from_context_prioritizes_missing_angles():
    result = related_questions_from_context(
        "Што е најважното ново во оваа вест?",
        "Свет",
        has_perspectives=True,
        has_multiple_sources=True,
        has_unclear_points=True,
    )

    assert result[0] == "Како се разликуваат изворите во известувањето?"
    assert "Што останува нејасно или непотврдено?" in result
