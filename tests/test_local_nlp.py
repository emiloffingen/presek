from local_nlp import (
    filter_cluster_tags,
    extract_cluster_tags_locally,
    is_valid_focus_entity,
    build_structured_answer_sections,
)


class TestTagFiltering:
    def test_filters_noise_and_time_fragments(self):
        tags = [
            "часа",
            "слушаме гласот",
            "Израел",
            "18:30",
            "Добронамерните",
            "Иран",
        ]

        assert filter_cluster_tags(tags) == ["Израел", "Иран"]

    def test_rejects_generic_fragment_entities(self):
        assert not is_valid_focus_entity("Подготвува Напади", None)
        assert not is_valid_focus_entity("Напади Ирански", None)
        assert is_valid_focus_entity("Израел", "country")


class TestClusterTagExtraction:
    def test_prefers_coherent_cluster_tags(self):
        titles = [
            "Израел подготвува напади врз ирански цели, тврдат извори",
            "Иран најавува одговор по израелски напади врз нуклеарни цели",
            "Трамп повика на воздржаност по ескалацијата меѓу Израел и Иран",
        ]
        entities = [
            {"entity_name": "Израел", "entity_type": "country"},
            {"entity_name": "Иран", "entity_type": "country"},
            {"entity_name": "Трамп", "entity_type": "person"},
            {"entity_name": "Подготвува Напади", "entity_type": "event"},
        ]

        tags = extract_cluster_tags_locally(titles, entity_names=entities, top_n=5)

        assert "Израел" in tags
        assert "Иран" in tags
        assert "Трамп" in tags
        assert "Подготвува Напади" not in tags


class TestStructuredAnswerSections:
    def test_source_differences_use_actual_titles_when_available(self):
        articles = [
            {"source": "МИА", "title": "Трамп: Вторник, 20:00 часот по источно време", "description": ""},
            {"source": "Reuters", "title": "Трамп најави говор за царини и економски мерки", "description": ""},
        ]

        sections = build_structured_answer_sections(
            "Главниот развој е потврден. Последиците сè уште не се целосно јасни.",
            articles,
            synthesis="",
            perspectives=[],
        )

        assert "МИА" in sections["source_differences"]
        assert "Reuters" in sections["source_differences"]
        assert "формулира развојот" in sections["source_differences"]
