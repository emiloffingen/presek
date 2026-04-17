import entities


def test_extract_entities_prefers_full_known_name_over_fragment(monkeypatch):
    monkeypatch.setattr(entities, "_get_spacy", lambda: None)

    result = entities.extract_entities(
        "Доналд Трамп повторно се појави во вестите. Трамп даде изјава.",
        max_entities=5,
    )

    names = [item["name"] for item in result]
    assert "Доналд Трамп" in names
    assert names.count("Доналд Трамп") == 1


def test_extract_entities_normalizes_common_latin_script_famous_people(monkeypatch):
    monkeypatch.setattr(entities, "_get_spacy", lambda: None)

    result = entities.extract_entities(
        "Donald Trump and Elon Musk met after comments about Volodymyr Zelenskyy.",
        max_entities=5,
    )

    names = [item["name"] for item in result]
    assert "Доналд Трамп" in names
    assert "Илон Маск" in names
    assert "Володимир Зеленски" in names


def test_extract_entities_regex_fallback_rejects_generic_sentence_fragments(monkeypatch):
    monkeypatch.setattr(entities, "_get_spacy", lambda: None)

    result = entities.extract_entities(
        "Голем Успех за тимот. Нова Анализа покажува раст. Доналд Трамп зборуваше подоцна.",
        max_entities=5,
    )

    names = [item["name"] for item in result]
    assert "Голем Успех" not in names
    assert "Нова Анализа" not in names
    assert "Доналд Трамп" in names
