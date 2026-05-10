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
        assert "Доналд Трамп" in tags
        assert "Подготвува Напади" not in tags

    def test_extract_keyphrases_locally_filters_source_noise_and_prefers_real_phrases(
        self,
    ):
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
        assert any(
            "100" in item or "120" in item for item in result["difference_points"]
        )

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

        assert any(
            "120" in item or "Стопанската комора" in item
            for item in result["open_points"]
        )

    def test_compare_cluster_sources_reuses_cached_result_for_same_articles(
        self, monkeypatch
    ):
        import nlp.generation

        nlp.generation._comparison_cache.clear()
        calls = {"count": 0}
        original = nlp.generation.extract_keyphrases_locally

        def counting_extract(*args, **kwargs):
            calls["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(
            nlp.generation, "extract_keyphrases_locally", counting_extract
        )
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

        assert any(item["angle"] == "Нијанси" for item in result["perspectives"])
        assert any(item["angle"] == "Отворено" for item in result["perspectives"])
        assert "Клучен развој" in result["summary"] or "Настан" in result["summary"]

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

        assert "Настан" in result["summary"]
        assert "Пакетот" in result["summary"]

    def test_synthesize_cluster_fallback_records_mode(self, monkeypatch):
        import nlp.generation

        events = []

        def record(event, **fields):
            events.append((event, fields))

        monkeypatch.setattr(nlp.generation, "record_runtime_event", record)
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

        assert ("local_synthesis_path", {"mode": "enhanced_fallback"}) in events


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
            "Трамп изјави дека во вторник ќе има обраќање. #економија #свет",
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

        assert "Клучен развој" in result["summary"]
        assert "Следено од 2 извори" in result["summary"]

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
                "description": "Се уште не е потвредeно кога точно ќе стартува пакетот.",
            },
        ]

        result = synthesize_cluster_fallback(articles)
        assert any(p["angle"] == "Нијанси" for p in result["perspectives"])
        assert any(p["angle"] == "Отворено" for p in result["perspectives"])


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

        assert "## Динамика на денот" in result
        assert "## Контекст и разлики" in result
        assert "- Клучен аспект:" in result or "- Зошто е важно:" in result

    def test_generate_daily_brief_fallback_prefers_cluster_synthesis_text(self):
        clusters = [
            {
                "title": "СДСМ: Партиско соопштение за дневната политика",
                "source": "МИА",
                "topic": "Политика",
                "description": "Општ партиски став без многу детали.",
                "cluster_summary": (
                    "Што се случува: Собраниската расправа за интерпелацијата влегува во завршна фаза.\n"
                    "Зошто е важно: Исходот ќе влијае врз темпото на политичката агенда."
                ),
                "source_count": 5,
            }
        ]

        result = generate_daily_brief_fallback(clusters)

        assert (
            "Собраниската расправа за интерпелацијата влегува во завршна фаза" in result
        )
        assert "Општ партиски став без многу детали" not in result

    def test_generate_daily_brief_fallback_strips_agency_boilerplate(self):
        clusters = [
            {
                "title": "СДСМ: Бараме локален референдум за рудникот",
                "source": "МИА",
                "topic": "Политика",
                "description": "Скопје, 19 април 2026 (МИА) - За најавата на Мицкоски за отворање рудник со антимон мора да има јавна дебата.",
                "source_count": 5,
            }
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "Скопје, 19 април 2026 (МИА) -" not in result

    def test_generate_daily_brief_fallback_intro_prefers_less_partisan_updates(self):
        clusters = [
            {
                "title": "СДСМ: Во очајна потрага по добра вест",
                "source": "МИА",
                "topic": "Политика",
                "description": "Партиско соопштение.",
                "source_count": 7,
            },
            {
                "title": "Земјотрес од 4,8 степени ја потресе Македонија",
                "source": "ММС",
                "topic": "Вести",
                "description": "Потресот е почувствуван во повеќе градови.",
                "cluster_summary": "Земјотрес од 4,8 степени е почувствуван во повеќе градови низ Македонија.",
                "source_count": 8,
            },
            {
                "title": "Бугарија денеска излегува на парламентарни избори",
                "source": "Reuters",
                "topic": "Политика",
                "description": "Гласањето се одржува денеска.",
                "cluster_summary": "Бугарија денеска гласа на парламентарни избори со неизвесен исход.",
                "source_count": 9,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert (
            "Земјотрес од 4,8 степени е почувствуван во повеќе градови низ Македонија"
            in result.splitlines()[2]
        )
        assert "СДСМ: Во очајна потрага по добра вест" not in result.splitlines()[2]

    def test_generate_daily_brief_fallback_keeps_required_sections_without_editorial_points(
        self,
    ):
        clusters = [
            {
                "title": "Бугарија денеска излегува на парламентарни избори",
                "source": "Reuters",
                "topic": "Политика",
                "description": "Гласањето се одржува денеска.",
                "cluster_summary": "Бугарија денеска гласа на парламентарни избори со неизвесен исход.",
                "source_count": 3,
            }
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "## Контекст и разлики" in result
        assert "### 1. Бугарија" in result
        assert "Темата се појавува низ" not in result

    def test_generate_daily_brief_fallback_reorders_body_away_from_penalized_titles(
        self,
    ):
        clusters = [
            {
                "title": "СДСМ: Во очајна потрага по добра вест",
                "source": "МИА",
                "topic": "Политика",
                "description": "Партиско соопштение.",
                "source_count": 8,
            },
            {
                "title": "Бугарија денеска излегува на парламентарни избори",
                "source": "Reuters",
                "topic": "Политика",
                "description": "Гласањето се одржува денеска.",
                "cluster_summary": "Бугарија денеска гласа на парламентарни избори со неизвесен исход.",
                "source_count": 7,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "### 1. Бугарија денеска излегува на парламентарни избори" in result

    def test_generate_daily_brief_fallback_dedupes_near_identical_story_slots(self):
        clusters = [
            {
                "title": "Северна Кореја повторно истрела балистички ракети",
                "source": "AP",
                "topic": "Вести",
                "description": "Ракетното лансирање предизвика меѓународни реакции.",
                "cluster_summary": "Северна Кореја повторно истрела балистички ракети.",
                "source_count": 5,
            },
            {
                "title": "Пјонгјанг повторно лансираше балистички ракети",
                "source": "Reuters",
                "topic": "Вести",
                "description": "Северна Кореја повторно истрела балистички ракети кон морето.",
                "cluster_summary": "Северна Кореја повторно истрела балистички ракети.",
                "source_count": 4,
            },
            {
                "title": "Бугарија денеска излегува на парламентарни избори",
                "source": "Reuters",
                "topic": "Политика",
                "description": "Гласањето се одржува денеска.",
                "cluster_summary": "Бугарија денеска гласа на парламентарни избори со неизвесен исход.",
                "source_count": 9,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert result.count("### ") == 2
        assert "### 3. Пјонгјанг повторно лансираше балистички ракети" not in result

    def test_generate_daily_brief_fallback_uses_distinct_description_context_for_importance(
        self,
    ):
        clusters = [
            {
                "title": "Северна Кореја повторно истрела балистички ракети",
                "source": "AP",
                "topic": "Вести",
                "description": "Ракетното лансирање предизвика итни реакции од соседните држави и сојузниците.",
                "source_count": 5,
            },
            {
                "title": "Гутереш го осуди нападот во кој беше убиен француски мировник на ОН во Либан",
                "source": "Reuters",
                "topic": "Вести",
                "description": "Нападот повторно отвори прашања за безбедноста на мировните мисии во јужен Либан.",
                "source_count": 4,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "итни реакции од соседните држави и сојузниците" in result
        assert "безбедноста на мировните мисии во јужен Либан" in result

    def test_generate_daily_brief_fallback_splits_security_heuristics_by_story_type(
        self,
    ):
        clusters = [
            {
                "title": "Северна Кореја повторно истрела балистички ракети",
                "source": "AP",
                "topic": "Вести",
                "description": "",
                "source_count": 5,
            },
            {
                "title": "Гутереш го осуди нападот во кој беше убиен француски мировник на ОН во Либан",
                "source": "Reuters",
                "topic": "Вести",
                "description": "",
                "source_count": 4,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "Динамика на денот" in result
        assert "Контекст и разлики" in result

    def test_generate_daily_brief_fallback_keeps_election_importance_outcome_oriented(
        self,
    ):
        clusters = [
            {
                "title": "Бугарија денеска излегува на парламентарни избори во последните пет години",
                "source": "Reuters",
                "topic": "Политика",
                "description": "Во Бугарија денеска се одржуваат парламентарни избори за состав на 52-рото Народно собрание.",
                "source_count": 9,
            }
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "Динамика на денот" in result
        assert "Бугарија" in result or "избори" in result
