from nlp import (
    filter_cluster_tags,
    extract_cluster_tags_locally,
    extract_keyphrases_locally,
    generate_daily_brief_fallback,
    is_valid_focus_entity,
    rewrite_to_serbian_locally,
    summarize_locally,
    summarize_article_fallback,
    compare_cluster_sources,
    synthesize_cluster_fallback,
)


class TestTagFiltering:
    def test_filters_noise_and_time_fragments(self):
        tags = [
            "casa",
            "slusame glasot",
            "Izrael",
            "18:30",
            "Dobronamernite",
            "Iran",
        ]

        assert filter_cluster_tags(tags) == ["Izrael", "Iran"]

    def test_rejects_generic_fragment_entities(self):
        assert not is_valid_focus_entity("Podgotvuva Napadi", None)
        assert not is_valid_focus_entity("Napadi Iranski", None)
        assert is_valid_focus_entity("Izrael", "country")


class TestClusterTagExtraction:
    def test_prefers_coherent_cluster_tags(self):
        titles = [
            "Izrael podgotvuva napadi vrz iranski celi, tvrdat izvori",
            "Iran najavuva odgovor po izraelski napadi vrz nuklearni celi",
            "Tramp povika na vozdrzanost po eskalacijata medju Izrael i Iran",
        ]
        entities = [
            {"entity_name": "Izrael", "entity_type": "country"},
            {"entity_name": "Iran", "entity_type": "country"},
            {"entity_name": "Tramp", "entity_type": "person"},
            {"entity_name": "Podgotvuva Napadi", "entity_type": "event"},
        ]

        tags = extract_cluster_tags_locally(titles, entity_names=entities, top_n=5)

        assert "Izrael" in tags
        assert "Iran" in tags
        assert "Donald Tramp" in tags
        assert "Podgotvuva Napadi" not in tags

    def test_extract_keyphrases_locally_filters_source_noise_and_prefers_real_phrases(
        self,
    ):
        text = (
            "Reuters javuva deka Vladata usvoi paket za energetska poddrska. "
            "Paketot za energetska poddrska vredi 120 milioni evra. "
            "AP pisuva deka merkite pocnuvaat vo Utorak."
        )

        phrases = extract_keyphrases_locally(text, top_n=5)

        assert any("paket" in item.lower() for item in phrases)
        assert not any(item.lower() == "reuters" for item in phrases)
        assert not any(item.lower() == "ap" for item in phrases)

    def test_prefers_repeated_explicit_entities_over_generic_tokens(self):
        titles = [
            "Evropska komisija predlaga nov paket merki za energija",
            "reakcija na Evropska komisija po raspravata za novi merki",
            "Liderite cekaat odluka od Evropska komisija",
        ]
        entities = [
            {"entity_name": "Evropska komisija", "entity_type": "organization"},
            {"entity_name": "Reuters", "entity_type": "organization"},
        ]

        tags = extract_cluster_tags_locally(titles, entity_names=entities, top_n=4)

        assert tags[0] == "Evropska komisija"
        assert "Reuters" not in tags


class TestClusterComparison:
    def test_compare_cluster_sources_finds_common_line_and_differences(self):
        articles = [
            {
                "source": "MIA",
                "title": "Izbori vo Utorak so 100 nabljuduvaci",
                "description": "MIA tvrdi deka podgotovkite se vo zavrsna faza.",
            },
            {
                "source": "Reuters",
                "title": "Fokusot e na reakciite i rokot za izbori",
                "description": "Reuters pisuva za 120 nabljuduvaci i mozni dopolnitelni merki.",
            },
            {
                "source": "AP",
                "title": "Izbori i reakcije na opozicijata",
                "description": "Se ocekuva dopolnitelna potvrda za brojkite.",
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
                "source": "MIA",
                "title": "Vladata usvoi paket za energetska poddrska",
                "description": "Paketot za energetska poddrska startuva vo Utorak so 120 milioni evra.",
            },
            {
                "source": "Reuters",
                "title": "Reakciite se vrzuvaat za paketot za energetska poddrska",
                "description": "Reuters naveduva deka paketot za energetska poddrska nosi merki za domacinstvata.",
            },
        ]

        result = compare_cluster_sources(articles)

        assert "vo fokus" in result["common_line"].lower()
        assert "energetska poddrska" in result["common_line"].lower()

    def test_compare_cluster_sources_surfaces_unique_entities_by_source(self):
        articles = [
            {
                "source": "MIA",
                "title": "Sredba medju Vladata i Sindikatot za nov paket",
                "description": "Vladata i Sindikatot razgovarale za pocetokot na merkite.",
            },
            {
                "source": "Reuters",
                "title": "Reuters javuva za reakcija od Stopanskata komora",
                "description": "Stopanskata komora bara dopolnitelni garancii za paketot.",
            },
        ]

        result = compare_cluster_sources(articles)

        assert any("Stopanskata komora" in item for item in result["difference_points"])

    def test_compare_cluster_sources_open_points_include_uncertain_unique_details(self):
        articles = [
            {
                "source": "MIA",
                "title": "Vladata najavi paket od 100 milioni evra",
                "description": "Merkite pocnuvaat vo Utorak.",
            },
            {
                "source": "Reuters",
                "title": "Reuters naveduva mozen siri opfat",
                "description": "Se ocekuva paketot da dostigne 120 milioni evra i da vkluci Stopanskata komora vo konsultaciite.",
            },
        ]

        result = compare_cluster_sources(articles)

        assert any(
            "120" in item or "Stopanskata komora" in item
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
                "source": "MIA",
                "title": "Vladata usvoi paket za energetska poddrska",
                "description": "Paketot za energetska poddrska startuva vo Utorak so 120 milioni evra.",
            },
            {
                "source": "Reuters",
                "title": "Reakciite se vrzuvaat za paketot za energetska poddrska",
                "description": "Reuters naveduva deka paketot za energetska poddrska nosi merki za domacinstvata.",
            },
        ]

        first = compare_cluster_sources(articles)
        second = compare_cluster_sources(articles)

        assert first == second
        assert calls["count"] == 1

    def test_synthesize_cluster_fallback_uses_comparison_output(self):
        articles = [
            {
                "source": "MIA",
                "title": "Paketot vleguva vo vladina procedura",
                "description": "Spored Vladata, merkite pocnuvaat vo Sreda.",
            },
            {
                "source": "Reuters",
                "title": "Reuters akcentira na rokot i reakciite",
                "description": "Se jos ne e potvrdeno koga tocno ce startuva paketot.",
            },
        ]

        result = synthesize_cluster_fallback(articles)

        assert any(item["angle"] == "Nijansi" for item in result["perspectives"])
        assert any(item["angle"] == "otvoreno" for item in result["perspectives"])
        assert "Klucen razvoj" in result["summary"] or "Nastan" in result["summary"]

    def test_synthesize_cluster_fallback_uses_confirmed_section(self):
        articles = [
            {
                "source": "MIA",
                "title": "Vladata usvoi paket za energetska poddrska",
                "description": "Paketot za energetska poddrska startuva vo Utorak so 120 milioni evra.",
            },
            {
                "source": "Reuters",
                "title": "Reakciite se vrzuvaat za paketot za energetska poddrska",
                "description": "Reuters naveduva deka paketot za energetska poddrska nosi merki za domacinstvata.",
            },
        ]

        result = synthesize_cluster_fallback(articles)

        assert "energetska poddrska" in result["summary"].lower()

    def test_synthesize_cluster_fallback_quality_gate_keeps_grounded_structure(self):
        articles = [
            {
                "source": "MIA",
                "title": "Paketot",
                "description": "",
            },
            {
                "source": "Reuters",
                "title": "Paketot",
                "description": "",
            },
        ]

        result = synthesize_cluster_fallback(articles)

        assert "Nastan" in result["summary"]
        assert "Paketot" in result["summary"]

    def test_synthesize_cluster_fallback_records_mode(self, monkeypatch):
        import nlp.generation

        events = []

        def record(event, **fields):
            events.append((event, fields))

        monkeypatch.setattr(nlp.generation, "record_runtime_event", record)
        articles = [
            {
                "source": "MIA",
                "title": "Vladata usvoi paket za energetska poddrska",
                "description": "Paketot za energetska poddrska startuva vo Utorak so 120 milioni evra.",
            },
            {
                "source": "Reuters",
                "title": "Reakciite se vrzuvaat za paketot za energetska poddrska",
                "description": "Reuters naveduva deka paketot za energetska poddrska nosi merki za domacinstvata.",
            },
        ]

        synthesize_cluster_fallback(articles)

        assert ("local_synthesis_path", {"mode": "enhanced_fallback"}) in events


class TestArticleSummaryFallback:
    def test_summarize_locally_prefers_information_dense_sentences_over_noise(self):
        text = (
            "FOTO: Galerija od nastanot. "
            "Vladata danas usvoi paket od 120 milioni evra za energetska poddrska na domacinstvata i malite kompanii. "
            "Premierot najavi deka merkite ce pocnat da vazat od Utorak po objavata vo Sluzben vesnik. "
            "#Ekonomija #vesti #najnovo."
        )

        result = summarize_locally(text, sentence_count=2)

        assert "120 milioni evra" in result
        assert "Utorak" in result or "utorak" in result.lower()
        assert "FOTO:" not in result
        assert "#Ekonomija" not in result

    def test_summarize_article_fallback_returns_clean_compact_text(self):
        result = summarize_article_fallback(
            "⚪ Tramp najavi novi carini",
            "Tramp izjavi deka vo Utorak ce ima obracanje. #Ekonomija #Svet",
        )

        assert "⚪" not in result
        assert "#Ekonomija" not in result
        assert "Tramp" in result


class TestLocalSerbianRewrite:
    def test_rewrites_common_english_news_copy(self):
        result = rewrite_to_serbian_locally(
            "Prime Minister announced new measures on Tuesday according to officials"
        )

        lowered = result.lower()
        assert "premijer" in lowered
        assert "mere" in lowered
        assert "utorak" in lowered

    def test_keeps_existing_serbian_text_clean(self):
        result = rewrite_to_serbian_locally("  Vladata   najavi   nov paket merki  ")
        assert result == "Vladata najavi nov paket merki."

    def test_synthesize_cluster_fallback_uses_common_line_in_summary(self):
        articles = [
            {
                "source": "MIA",
                "title": "Vladata usvoi paket za poddrska",
                "description": "Poveceto merki startuvaat vo Utorak so paket od 120 milioni evra.",
            },
            {
                "source": "Reuters",
                "title": "Fokusot e na reakciite za paketot za poddrska",
                "description": "I Reuters pisuva za paketot od 120 milioni evra i vladinata odluka.",
            },
        ]

        result = synthesize_cluster_fallback(articles)

        assert "Klucen razvoj" in result["summary"]
        assert "Sledeno od 2 izvori" in result["summary"]

    def test_synthesize_cluster_fallback_uses_cleaner_open_line_label(self):
        articles = [
            {
                "source": "MIA",
                "title": "Paketot vleguva vo vladina procedura",
                "description": "Spored Vladata, merkite pocnuvaat vo Sreda.",
            },
            {
                "source": "Reuters",
                "title": "Reuters akcentira na rokot i reakciite",
                "description": "Se jos ne e potvredeno koga tocno ce startuva paketot.",
            },
        ]

        result = synthesize_cluster_fallback(articles)
        assert any(p["angle"] == "Nijansi" for p in result["perspectives"])
        assert any(p["angle"] == "otvoreno" for p in result["perspectives"])


class TestLocalBriefingFallback:
    def test_generate_daily_brief_fallback_uses_editorial_sections(self):
        clusters = [
            {
                "title": "Vladata usvoi paket za poddrska",
                "source": "MIA",
                "topic": "Ekonomija",
                "description": "Paketot vredi 120 milioni evra i startuva vo Utorak.",
                "source_count": 4,
                "difference_point": "Izvorite se razlikuvaat okolu rokot za pocetok.",
                "open_point": "ostaje da se potvrdi tocniot datum na start.",
            },
            {
                "title": "Opozicijata bara dopolnitelna rasprava",
                "source": "Reuters",
                "topic": "Politika",
                "description": "Opozicijata bara dopolnitelni objasnuvanja za merkite.",
                "source_count": 3,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "## Dinamika na denot" in result
        assert "## kontekst i razliki" in result
        assert "- Klucen aspekt:" in result or "- Zosto e vazno:" in result

    def test_generate_daily_brief_fallback_prefers_cluster_synthesis_text(self):
        clusters = [
            {
                "title": "SDSM: Partisko soopstenie za dnevnata Politika",
                "source": "MIA",
                "topic": "Politika",
                "description": "Opst partiski stav bez mnogu detali.",
                "cluster_summary": (
                    "Sto se slucuva: Sobraniskata rasprava za interpelacijata vleguva vo zavrsna faza.\n"
                    "Zosto e vazno: Ishodot ce vlijae vrz tempoto na politickata agenda."
                ),
                "source_count": 5,
            }
        ]

        result = generate_daily_brief_fallback(clusters)

        assert (
            "Sobraniskata rasprava za interpelacijata vleguva vo zavrsna faza" in result
        )
        assert "Opst partiski stav bez mnogu detali" not in result

    def test_generate_daily_brief_fallback_strips_agency_boilerplate(self):
        clusters = [
            {
                "title": "SDSM: Barame lokalen referendum za rudnikot",
                "source": "MIA",
                "topic": "Politika",
                "description": "Beograd, 19 april 2026 (MIA) - Za najavata na Mickoski za otvoranje rudnik so antimon mora da ima javna debata.",
                "source_count": 5,
            }
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "Beograd, 19 april 2026 (MIA) -" not in result

    def test_generate_daily_brief_fallback_intro_prefers_less_partisan_updates(self):
        clusters = [
            {
                "title": "SDSM: Vo ocajna potraga po dobra vest",
                "source": "MIA",
                "topic": "Politika",
                "description": "Partisko soopstenie.",
                "source_count": 7,
            },
            {
                "title": "Zemjotres od 4,8 stepeni me potrese Srbija",
                "source": "MMS",
                "topic": "vesti",
                "description": "Potresot e pocuvstvuvan vo povece gradovi.",
                "cluster_summary": "Zemjotres od 4,8 stepeni e pocuvstvuvan vo povece gradovi niz Srbija.",
                "source_count": 8,
            },
            {
                "title": "Bugarija danas izleguva na parlamentarni izbori",
                "source": "Reuters",
                "topic": "Politika",
                "description": "Glasanjeto se odrzuva danas.",
                "cluster_summary": "Bugarija danas glasa na parlamentarni izbori so neizvesen ishod.",
                "source_count": 9,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert (
            "Zemjotres od 4,8 stepeni e pocuvstvuvan vo povece gradovi niz Srbija"
            in result.splitlines()[2]
        )
        assert "SDSM: Vo ocajna potraga po dobra vest" not in result.splitlines()[2]

    def test_generate_daily_brief_fallback_keeps_required_sections_without_editorial_points(
        self,
    ):
        clusters = [
            {
                "title": "Bugarija danas izleguva na parlamentarni izbori",
                "source": "Reuters",
                "topic": "Politika",
                "description": "Glasanjeto se odrzuva danas.",
                "cluster_summary": "Bugarija danas glasa na parlamentarni izbori so neizvesen ishod.",
                "source_count": 3,
            }
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "## kontekst i razliki" in result
        assert "### 1. Bugarija" in result
        assert "Temata se pojavuva niz" not in result

    def test_generate_daily_brief_fallback_reorders_body_away_from_penalized_titles(
        self,
    ):
        clusters = [
            {
                "title": "SDSM: Vo ocajna potraga po dobra vest",
                "source": "MIA",
                "topic": "Politika",
                "description": "Partisko soopstenie.",
                "source_count": 8,
            },
            {
                "title": "Bugarija danas izleguva na parlamentarni izbori",
                "source": "Reuters",
                "topic": "Politika",
                "description": "Glasanjeto se odrzuva danas.",
                "cluster_summary": "Bugarija danas glasa na parlamentarni izbori so neizvesen ishod.",
                "source_count": 7,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "### 1. Bugarija danas izleguva na parlamentarni izbori" in result

    def test_generate_daily_brief_fallback_dedupes_near_identical_story_slots(self):
        clusters = [
            {
                "title": "Severna Koreja povtorno istrela balisticki raketi",
                "source": "AP",
                "topic": "vesti",
                "description": "Raketnoto lansiranje predizvika medjunarodni reakcije.",
                "cluster_summary": "Severna Koreja povtorno istrela balisticki raketi.",
                "source_count": 5,
            },
            {
                "title": "Pjongjang povtorno lansirase balisticki raketi",
                "source": "Reuters",
                "topic": "vesti",
                "description": "Severna Koreja povtorno istrela balisticki raketi kon moreto.",
                "cluster_summary": "Severna Koreja povtorno istrela balisticki raketi.",
                "source_count": 4,
            },
            {
                "title": "Bugarija danas izleguva na parlamentarni izbori",
                "source": "Reuters",
                "topic": "Politika",
                "description": "Glasanjeto se odrzuva danas.",
                "cluster_summary": "Bugarija danas glasa na parlamentarni izbori so neizvesen ishod.",
                "source_count": 9,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert result.count("### ") == 2
        assert "### 3. Pjongjang povtorno lansirase balisticki raketi" not in result

    def test_generate_daily_brief_fallback_uses_distinct_description_context_for_importance(
        self,
    ):
        clusters = [
            {
                "title": "Severna Koreja povtorno istrela balisticki raketi",
                "source": "AP",
                "topic": "vesti",
                "description": "Raketnoto lansiranje predizvika itni reakcije od sosednite drzavi i sojuznicite.",
                "source_count": 5,
            },
            {
                "title": "Guteres ga osudi napadot vo koj bese ubien francuski mirovnik na ON vo Liban",
                "source": "Reuters",
                "topic": "vesti",
                "description": "Napadot povtorno otvori prasanja za bezbednosta na mirovnite misii vo juzen Liban.",
                "source_count": 4,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "itni reakcije od sosednite drzavi i sojuznicite" in result
        assert "bezbednosta na mirovnite misii vo juzen Liban" in result

    def test_generate_daily_brief_fallback_splits_security_heuristics_by_story_type(
        self,
    ):
        clusters = [
            {
                "title": "Severna Koreja povtorno istrela balisticki raketi",
                "source": "AP",
                "topic": "vesti",
                "description": "",
                "source_count": 5,
            },
            {
                "title": "Guteres ga osudi napadot vo koj bese ubien francuski mirovnik na ON vo Liban",
                "source": "Reuters",
                "topic": "vesti",
                "description": "",
                "source_count": 4,
            },
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "Dinamika na denot" in result
        assert "kontekst i razliki" in result

    def test_generate_daily_brief_fallback_keeps_election_importance_outcome_oriented(
        self,
    ):
        clusters = [
            {
                "title": "Bugarija danas izleguva na parlamentarni izbori vo poslednite pet godini",
                "source": "Reuters",
                "topic": "Politika",
                "description": "Vo Bugarija danas se odrzuvaat parlamentarni izbori za sostav na 52-roto Narodno sobranie.",
                "source_count": 9,
            }
        ]

        result = generate_daily_brief_fallback(clusters)

        assert "Dinamika na denot" in result
        assert "Bugarija" in result or "izbori" in result
