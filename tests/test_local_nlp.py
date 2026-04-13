from local_nlp import (
    filter_cluster_tags,
    extract_cluster_tags_locally,
    extract_keyphrases_locally,
    generate_daily_brief_fallback,
    is_valid_focus_entity,
    rewrite_to_macedonian_locally,
    summarize_locally,
    summarize_article_fallback,
    compare_cluster_sources,
    synthesize_cluster_fallback,
)
import local_nlp


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

    def test_extract_keyphrases_locally_filters_source_noise_and_prefers_real_phrases(self):
        text = (
            "Reuters јавува дека Владата усвои пакет за енергетска поддршка. "
            "Пакетот за енергетска поддршка вреди 120 милиони евра. "
            "AP пишува дека мерките почнуваат во вторник."
        )

        phrases = extract_keyphrases_locally(text, top_n=5)

        assert any("пакет" in item.lower() for item in phrases)
        assert not any(item.lower() == "reuters" for item in phrases)
        assert not any(item.lower() == "ap" for item in phrases)

    def test_prefers_repeated_explicit_entities_over_generic_tokens(self):
        titles = [
            "Европска комисија предлага нов пакет мерки за енергија",
            "Реакција на Европска комисија по расправата за нови мерки",
            "Лидерите чекаат одлука од Европска комисија",
        ]
        entities = [
            {"entity_name": "Европска комисија", "entity_type": "organization"},
            {"entity_name": "Reuters", "entity_type": "organization"},
        ]

        tags = extract_cluster_tags_locally(titles, entity_names=entities, top_n=4)

        assert tags[0] == "Европска комисија"
        assert "Reuters" not in tags


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

    def test_compare_cluster_sources_uses_phrase_based_common_line(self):
        articles = [
            {
                "source": "МИА",
                "title": "Владата усвои пакет за енергетска поддршка",
                "description": "Пакетот за енергетска поддршка стартува во вторник со 120 милиони евра.",
            },
            {
                "source": "Reuters",
                "title": "Реакциите се врзуваат за пакетот за енергетска поддршка",
                "description": "Reuters наведува дека пакетот за енергетска поддршка носи мерки за домаќинствата.",
            },
        ]

        result = compare_cluster_sources(articles)

        assert "во фокус" in result["common_line"].lower()
        assert "енергетска поддршка" in result["common_line"].lower()

    def test_compare_cluster_sources_surfaces_unique_entities_by_source(self):
        articles = [
            {
                "source": "МИА",
                "title": "Средба меѓу Владата и Синдикатот за нов пакет",
                "description": "Владата и Синдикатот разговарале за почетокот на мерките.",
            },
            {
                "source": "Reuters",
                "title": "Reuters јавува за реакција од Стопанската комора",
                "description": "Стопанската комора бара дополнителни гаранции за пакетот.",
            },
        ]

        result = compare_cluster_sources(articles)

        assert any("Стопанската комора" in item for item in result["difference_points"])

    def test_compare_cluster_sources_open_points_include_uncertain_unique_details(self):
        articles = [
            {
                "source": "МИА",
                "title": "Владата најави пакет од 100 милиони евра",
                "description": "Мерките почнуваат во вторник.",
            },
            {
                "source": "Reuters",
                "title": "Reuters наведува можен поширок опфат",
                "description": "Се очекува пакетот да достигне 120 милиони евра и да вклучи Стопанската комора во консултациите.",
            },
        ]

        result = compare_cluster_sources(articles)

        assert any("120" in item or "Стопанската комора" in item for item in result["open_points"])

    def test_compare_cluster_sources_reuses_cached_result_for_same_articles(self, monkeypatch):
        local_nlp._comparison_cache.clear()
        calls = {"count": 0}
        original = local_nlp.extract_keyphrases_locally

        def counting_extract(*args, **kwargs):
            calls["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(local_nlp, "extract_keyphrases_locally", counting_extract)
        articles = [
            {
                "source": "МИА",
                "title": "Владата усвои пакет за енергетска поддршка",
                "description": "Пакетот за енергетска поддршка стартува во вторник со 120 милиони евра.",
            },
            {
                "source": "Reuters",
                "title": "Реакциите се врзуваат за пакетот за енергетска поддршка",
                "description": "Reuters наведува дека пакетот за енергетска поддршка носи мерки за домаќинствата.",
            },
        ]

        first = compare_cluster_sources(articles)
        second = compare_cluster_sources(articles)

        assert first == second
        assert calls["count"] == 1

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
        assert "Каде се разликуваат изворите" in result["summary"]
        assert "Што останува отворено" in result["summary"]

    def test_synthesize_cluster_fallback_uses_confirmed_section(self):
        articles = [
            {
                "source": "МИА",
                "title": "Владата усвои пакет за енергетска поддршка",
                "description": "Пакетот за енергетска поддршка стартува во вторник со 120 милиони евра.",
            },
            {
                "source": "Reuters",
                "title": "Реакциите се врзуваат за пакетот за енергетска поддршка",
                "description": "Reuters наведува дека пакетот за енергетска поддршка носи мерки за домаќинствата.",
            },
        ]

        result = synthesize_cluster_fallback(articles)

        assert "Што е потврдено" in result["summary"]
        assert "енергетска поддршка" in result["summary"].lower()

    def test_synthesize_cluster_fallback_quality_gate_keeps_grounded_structure(self):
        articles = [
            {
                "source": "МИА",
                "title": "Пакетот",
                "description": "",
            },
            {
                "source": "Reuters",
                "title": "Пакетот",
                "description": "",
            },
        ]

        result = synthesize_cluster_fallback(articles)

        assert "Што се случува" in result["summary"]
        assert "Покриеност" in result["summary"]
        assert "Пакетот" in result["summary"]

    def test_synthesize_cluster_fallback_records_mode(self, monkeypatch):
        events = []

        def record(event, **fields):
            events.append((event, fields))

        monkeypatch.setattr(local_nlp, "record_runtime_event", record)
        articles = [
            {
                "source": "МИА",
                "title": "Владата усвои пакет за енергетска поддршка",
                "description": "Пакетот за енергетска поддршка стартува во вторник со 120 милиони евра.",
            },
            {
                "source": "Reuters",
                "title": "Реакциите се врзуваат за пакетот за енергетска поддршка",
                "description": "Reuters наведува дека пакетот за енергетска поддршка носи мерки за домаќинствата.",
            },
        ]

        synthesize_cluster_fallback(articles)

        assert ("local_synthesis_path", {"mode": "full"}) in events

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


class TestLocalMacedonianRewrite:
    def test_rewrites_common_english_news_copy(self):
        result = rewrite_to_macedonian_locally(
            "Prime Minister announced new measures on Tuesday according to officials"
        )

        lowered = result.lower()
        assert "премиерот" in lowered
        assert "мерки" in lowered
        assert "вторник" in lowered
        assert "официјални претставници" in lowered or "според" in lowered

    def test_keeps_existing_macedonian_text_clean(self):
        result = rewrite_to_macedonian_locally("  Владата   најави   нов пакет мерки  ")
        assert result == "Владата најави нов пакет мерки"

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
