from local_nlp import (
    filter_cluster_tags,
    extract_cluster_tags_locally,
    generate_daily_brief_fallback,
    is_valid_focus_entity,
    summarize_locally,
    summarize_article_fallback,
    build_structured_answer_sections,
    compare_cluster_sources,
    synthesize_cluster_fallback,
    answer_cluster_question_locally,
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

    def test_source_differences_and_unclear_points_use_comparison_logic(self):
        articles = [
            {
                "source": "МИА",
                "title": "Владата најави пакет од 100 милиони евра",
                "description": "Според Владата, мерките стапуваат од вторник.",
            },
            {
                "source": "Reuters",
                "title": "Фокусот е на рокот и чекорите за пакетот",
                "description": "Агенцијата наведува дека 120 милиони евра се спомнуваат како можен опфат.",
            },
        ]

        sections = build_structured_answer_sections(
            "Главниот развој е пакетот. Последиците сè уште не се сосема јасни.",
            articles,
            synthesis="",
            perspectives=[],
        )

        assert "100" in sections["source_differences"] or "120" in sections["source_differences"]
        assert sections["unclear_points"]
        assert any("рокови" in item.lower() or "потврди" in item.lower() or "непотврд" in item.lower() for item in sections["unclear_points"])


class TestClusterComparison:
    def test_compare_cluster_sources_finds_common_line_and_differences(self):
        articles = [
            {
                "source": "МИА",
                "title": "Избори во вторник со 100 набљудувачи",
                "description": "МИА тврди дека подготовките се во завршна фаза.",
            },
            {
                "source": "Reuters",
                "title": "Фокусот е на реакциите и рокот за избори",
                "description": "Reuters пишува за 120 набљудувачи и можни дополнителни мерки.",
            },
            {
                "source": "AP",
                "title": "Избори и реакции на опозицијата",
                "description": "Се очекува дополнителна потврда за бројките.",
            },
        ]

        result = compare_cluster_sources(articles)

        assert result["common_line"]
        assert result["difference_points"]
        assert result["open_points"]
        assert any("100" in item or "120" in item for item in result["difference_points"])

    def test_synthesize_cluster_fallback_uses_comparison_output(self):
        articles = [
            {
                "source": "МИА",
                "title": "Пакетот влегува во владина процедура",
                "description": "Според Владата, мерките почнуваат во среда.",
            },
            {
                "source": "Reuters",
                "title": "Reuters акцентира на рокот и реакциите",
                "description": "Се уште не е потврдено кога точно ќе стартува пакетот.",
            },
        ]

        result = synthesize_cluster_fallback(articles)

        assert any(item["angle"] == "Различни акценти" for item in result["perspectives"])
        assert any(item["angle"] == "Што останува отворено" for item in result["perspectives"])

    def test_local_answers_use_comparison_for_differences_and_open_points(self):
        articles = [
            {
                "source": "МИА",
                "title": "Владата најави пакет од 100 милиони евра",
                "description": "Мерките почнуваат во вторник.",
            },
            {
                "source": "Reuters",
                "title": "Reuters акцентира на рокот и реакциите",
                "description": "Се очекува пакетот да изнесува 120 милиони евра.",
            },
        ]

        diff_answer = answer_cluster_question_locally("Како се разликуваат изворите?", articles)
        unclear_answer = answer_cluster_question_locally("Што е нејасно или непотврдено?", articles)

        assert "100" in diff_answer["answer"] or "120" in diff_answer["answer"]
        assert "потврд" in unclear_answer["answer"].lower() or "развива" in unclear_answer["answer"].lower()
        assert diff_answer["answer"].startswith("Изворите најмногу се разликуваат")
        assert unclear_answer["answer"].startswith("Најотворени остануваат")

    def test_local_answers_use_cleaner_main_development_intro(self):
        articles = [
            {
                "source": "МИА",
                "title": "Владата најави пакет од 100 милиони евра",
                "description": "Мерките почнуваат во вторник.",
            },
            {
                "source": "Reuters",
                "title": "Reuters акцентира на рокот и реакциите",
                "description": "Се очекува пакетот да изнесува 120 милиони евра.",
            },
        ]

        answer = answer_cluster_question_locally("Што е најважното ново?", articles)

        assert answer["answer"].startswith("Во овој момент, главниот развој е:")


class TestArticleSummaryFallback:
    def test_summarize_locally_prefers_information_dense_sentences_over_noise(self):
        text = (
            "ФОТО: Галерија од настанот. "
            "Владата денеска усвои пакет од 120 милиони евра за енергетска поддршка на домаќинствата и малите компании. "
            "Премиерот најави дека мерките ќе почнат да важат од вторник по објавата во Службен весник. "
            "#економија #вести #најново."
        )

        result = summarize_locally(text, sentence_count=2)

        assert "120 милиони евра" in result
        assert "вторник" in result.lower()
        assert "ФОТО:" not in result
        assert "#економија" not in result

    def test_summarize_article_fallback_returns_clean_compact_text(self):
        result = summarize_article_fallback(
            "⚪ Трамп најави нови царини",
            "Трамп изјави дека во вторник ќе има обраќање. #економија #свет"
        )

        assert "⚪" not in result
        assert "#економија" not in result
        assert "Трамп" in result

    def test_synthesize_cluster_fallback_uses_common_line_in_summary(self):
        articles = [
            {
                "source": "МИА",
                "title": "Владата усвои пакет за поддршка",
                "description": "Повеќето мерки стартуваат во вторник со пакет од 120 милиони евра.",
            },
            {
                "source": "Reuters",
                "title": "Фокусот е на реакциите за пакетот за поддршка",
                "description": "И Reuters пишува за пакетот од 120 милиони евра и владината одлука.",
            },
        ]

        result = synthesize_cluster_fallback(articles)

        assert "Заедничка линија" in result["summary"]
        assert "Што се случува" in result["summary"]
        assert "Покриеност" in result["summary"]

    def test_synthesize_cluster_fallback_uses_cleaner_open_line_label(self):
        articles = [
            {
                "source": "МИА",
                "title": "Пакетот влегува во владина процедура",
                "description": "Според Владата, мерките почнуваат во среда.",
            },
            {
                "source": "Reuters",
                "title": "Reuters акцентира на рокот и реакциите",
                "description": "Се уште не е потврдено кога точно ќе стартува пакетот.",
            },
        ]

        result = synthesize_cluster_fallback(articles)

        assert "Што останува отворено" in result["summary"] or "Следно за следење" in result["summary"]


class TestLocalBriefingFallback:
    def test_generate_daily_brief_fallback_uses_editorial_sections(self):
        clusters = [
            {
                "title": "Владата усвои пакет за поддршка",
                "source": "МИА",
                "topic": "Економија",
                "description": "Пакетот вреди 120 милиони евра и стартува во вторник.",
                "source_count": 4,
                "difference_point": "Изворите се разликуваат околу рокот за почеток.",
                "open_point": "Останува да се потврди точниот датум на старт.",
            },
            {
                "title": "Опозицијата бара дополнителна расправа",
                "source": "Reuters",
                "topic": "Политика",
                "description": "Опозицијата бара дополнителни објаснувања за мерките.",
                "source_count": 3,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "## Што го движи денот" in result
        assert "## Каде се разликува известувањето" in result
        assert "## Што да се следи понатаму" in result
        assert "- Што се менува:" in result
        assert "- Зошто е важно:" in result
