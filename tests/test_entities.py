import core.entities as entities


def test_extract_entities_prefers_full_known_name_over_fragment(monkeypatch):
    monkeypatch.setattr(entities, "_get_spacy", lambda: None)

    result = entities.extract_entities(
        "Donald Tramp povtorno se pojavi vo vestite. Tramp dade izjava.",
        max_entities=5,
    )

    names = [item["name"] for item in result]
    assert "Donald Tramp" in names
    assert names.count("Donald Tramp") == 1


def test_extract_entities_normalizes_common_latin_script_famous_people(monkeypatch):
    monkeypatch.setattr(entities, "_get_spacy", lambda: None)

    result = entities.extract_entities(
        "Donald Trump and Elon Musk met after comments about Volodymyr Zelenskyy.",
        max_entities=5,
    )

    names = [item["name"] for item in result]
    assert "Donald Tramp" in names
    assert "Ilon Mask" in names
    assert "Volodimir Zelenski" in names


def test_extract_entities_regex_fallback_rejects_generic_sentence_fragments(
    monkeypatch,
):
    monkeypatch.setattr(entities, "_get_spacy", lambda: None)

    result = entities.extract_entities(
        "Golem Uspeh za timot. nova Analiza pokazuva rast. Donald Tramp zboruvase podocna.",
        max_entities=5,
    )

    names = [item["name"] for item in result]
    assert "Golem Uspeh" not in names
    assert "nova Analiza" not in names
    assert "Donald Tramp" in names


def test_normalize_person_surface_name_title_cases_lowercase_person():
    assert (
        entities.normalize_person_surface_name("hristijan mickoski")
        == "Hristijan Mickoski"
    )


def test_normalize_person_surface_name_restores_known_surname_first_person():
    assert (
        entities.normalize_person_surface_name("mickoski hristijan")
        == "Hristijan Mickoski"
    )


def test_normalize_person_surface_name_keeps_non_person_tags_stable():
    assert entities.normalize_person_surface_name("Ekonomija") == "Ekonomija"
