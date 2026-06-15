from nlp import (
    compare_cluster_sources,
    extract_cluster_tags_locally,
    extract_keyphrases_locally,
    filter_cluster_tags,
    generate_daily_brief_fallback,
    is_valid_focus_entity,
    rewrite_to_serbian_locally,
    summarize_article_fallback,
    summarize_locally,
    synthesize_cluster_fallback,
)
from nlp.local_nlp import classify_news_quality_locally


class TestLocalNewsQualityClassifier:
    def test_classifies_cyrillic_hard_news_as_high_value(self):
        result = classify_news_quality_locally(
            "Владата усвои буџет со нови мерки за пензии",
            "Министерството соопшти дека пакетот вреди 120 милиони евра и ќе важи од следниот месец.",
        )

        assert result["score"] >= 0.6
        assert result["is_hard_news"]
        assert result["hard_matches"] >= 2
        assert result["public_interest_matches"] >= 1

    def test_rejects_clickbait_soft_content(self):
        result = classify_news_quality_locally(
            "ŠOKANTNO!!! Nećete verovati šta zvezde predviđaju",
            "Horoskop za vikend otkriva veliki preokret, pogledajte foto galeriju i viralni hit.",
        )

        assert result["score"] < 0.3
        assert not result["is_hard_news"]
        assert result["reason"] == "Low Quality / Junk"
        assert result["clickbait_matches"] >= 2

    def test_preserves_public_interest_story_with_photo_label(self):
        result = classify_news_quality_locally(
            "FOTO: Skupština raspravlja o zakonu o energetici",
            "Ministarstvo navodi da zakon utiče na cene struje za domaćinstva i budžet za narednu godinu.",
        )

        assert result["score"] >= 0.55
        assert result["is_hard_news"]
        assert result["hard_matches"] >= 2


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

    def test_repairs_diacritic_split_fragments(self):
        assert filter_cluster_tags(["Osumnji enih"]) == ["Osumnjičenih"]
        assert filter_cluster_tags(["osumnjičenih"]) == ["Osumnjičenih"]

    def test_preserves_multi_word_entities_without_diacritic_split(self):
        tags = filter_cluster_tags(["Evropska komisija", "Donald Tramp"])
        assert "Evropska komisija" in tags
        assert "Donald Tramp" in tags

    def test_keeps_cyrillic_tags_intact(self):
        tags = filter_cluster_tags(["Осумњичени", "Скопје"])
        assert "Осумњичени" in tags
        assert "Скопје" in tags

    def test_extract_cluster_tags_preserves_serbian_diacritics(self):
        titles = [
            "Policija uhapsila osumnjičenih u Beogradu nakon racije",
            "Tri osumnjičena lica privedena u centru grada",
        ]
        tags = extract_cluster_tags_locally(titles, top_n=6)
        assert not any(" " in tag and tag.endswith("enih") for tag in tags)
        assert any("osumnji" in tag.casefold() for tag in tags) or any(
            tag.casefold() == "beograd" for tag in tags
        )

    def test_rejects_generic_fragment_entities(self):
        assert not is_valid_focus_entity("Podgotvuva Napadi", None)
        assert not is_valid_focus_entity("Napadi Iranski", None)
        assert not is_valid_focus_entity("Otkazao", None)
        assert not is_valid_focus_entity("Pogledaj", None)
        assert not is_valid_focus_entity("Otvaranj", None)
        assert not is_valid_focus_entity("Student", None)
        assert not is_valid_focus_entity("Miljenik", None)
        assert not is_valid_focus_entity("Srba", None)
        assert is_valid_focus_entity("Izrael", "country")

    def test_normalizes_locative_entity_surfaces(self):
        from nlp.keywords import normalize_focus_entity_surface

        assert normalize_focus_entity_surface("Beogradu") == "Beograd"
        assert normalize_focus_entity_surface("Evropi") == "Evropa"
        assert normalize_focus_entity_surface("Kosovu") == "Kosovo"


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
        assert any("100" in item or "120" in item for item in result["difference_points"])

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

        assert "во фокус" in result["common_line"].lower()
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

        assert any("120" in item or "Stopanskata komora" in item for item in result["open_points"])

    def test_compare_cluster_sources_skips_fake_nuance_for_same_headline(self):
        articles = [
            {
                "source": "Insajder",
                "title": "Pad cena nafte u svetu nakon najave sporazuma SAD i Irana",
                "description": "Insajder prenosi da su cene nafte pale posle najave mogućeg sporazuma.",
            },
            {
                "source": "RTS",
                "title": "Pad cena nafte u svetu nakon najave sporazuma SAD i Irana",
                "description": "RTS prenosi isti razvoj i rast prometa na azijskim berzama.",
            },
        ]

        result = compare_cluster_sources(articles, lang="sr")

        assert not any("najdirektnije" in item or "više naglašava" in item for item in result["difference_points"])
        assert not any("ostaju nepotvrđeni kod Insajder, RTS" in item for item in result["open_points"])

    def test_synthesize_cluster_fallback_avoids_repeated_key_development_detail(self):
        repeated = "Cene nafte su značajno pale nakon najave mogućeg sporazuma SAD i Irana."
        articles = [
            {"source": "Insajder", "title": repeated, "description": repeated},
            {"source": "RTS", "title": repeated, "description": repeated},
            {"source": "Blic", "title": repeated, "description": "Azijske berze beleže rast prometa posle iste najave."},
        ]

        result = synthesize_cluster_fallback(articles, lang="sr")

        assert "prati 3 izvora" in result["summary"].lower()
        assert result["summary"].count("Cene nafte su značajno pale") == 1

    def test_synthesize_cluster_fallback_cleans_repetitive_editorial_narrative(self):
        articles = [
            {
                "source": "Insajder",
                "title": "Pad cena nafte u svetu nakon najave o postizanju sporazuma između SAD i Irana",
                "description": "Cene nafte su značajno pale, a promet na azijskim berzama je u porastu nakon najave o mogućem postizanju sporazuma.",
            },
            {
                "source": "RTS",
                "title": "Pad cena nafte u svetu nakon najave o postizanju sporazuma između SAD i Irana",
                "description": "Cene nafte su značajno pale, a promet na azijskim berzama je u porastu nakon najave o mogućem postizanju sporazuma.",
            },
            {
                "source": "Blic",
                "title": "Nafta pojeftinila dok berze rastu posle najave sporazuma",
                "description": "Azijska tržišta beleže rast prometa posle najave diplomatskog dogovora.",
            },
        ]

        result = synthesize_cluster_fallback(articles, lang="sr")
        narrative = result["generated_article"]

        assert "Pad Cena Naf" not in narrative
        assert "najdirektnije formuliše" not in narrative
        assert "više naglašava" not in narrative
        assert "Detalji oko ovog razvoja ostaju nepotvrđeni" not in narrative
        assert narrative.count("Cene nafte su značajno pale") <= 1

    def test_compare_cluster_sources_reuses_cached_result_for_same_articles(self, monkeypatch):
        import nlp.generation

        nlp.generation._comparison_cache.clear()
        calls = {"count": 0}
        original = nlp.generation.extract_keyphrases_locally

        def counting_extract(*args, **kwargs):
            calls["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(nlp.generation, "extract_keyphrases_locally", counting_extract)
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

        assert any(item["angle"] == "Нијанси" for item in result["perspectives"])
        assert any(item["angle"] == "отворено" for item in result["perspectives"])
        assert "merkite pocnuvaat vo Sreda" in result["summary"]

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

    def test_synthesize_cluster_fallback_prefers_target_language_lead(self):
        articles = [
            {
                "source": "Telegraf",
                "title": "Tramp najavio da ce prekrsiti protokol",
                "description": "Donald Tramp izjavio je da ce razgovarati...",
                "country": "RS",
            },
            {
                "source": "Vecer",
                "title": "Tramp najavi prekrsivanje na protokol",
                "description": "Donald Tramp najavi deka ce razgovara...",
                "country": "MK",
            },
        ]

        # For lang = "mk", it should prefer the MK article ("Vecer")
        result_mk = synthesize_cluster_fallback(articles, lang="mk")
        assert "Tramp najavi" in result_mk["synthetic_headline"]

        # For lang = "sr", it should prefer the RS article ("Telegraf")
        result_sr = synthesize_cluster_fallback(articles, lang="sr")
        assert "Tramp najavio" in result_sr["synthetic_headline"]

    def test_synthesize_cluster_fallback_fuses_multiple_sources(self):
        articles = [
            {
                "source": "Sitel",
                "title": "Novi merki za namaluvanje na cenite",
                "description": "Vladata donese odluka za zamrznuvanje na cenite na osnovnite prehrambeni proizvodi od slednata nedela.",
                "country": "MK",
            },
            {
                "source": "Kanal 5",
                "title": "Osnovnite namirnici so zamrznati ceni",
                "description": "Graganite ja pozdravija novata odluka no baraat i pogolemi plati kako dolgorocno resenie.",
                "country": "MK",
            },
            {
                "source": "Vecer",
                "title": "Novi merki za cenite na hranata",
                "description": "Vladata donese odluka za zamrznuvanje na cenite na osnovnite prehrambeni proizvodi od slednata nedela.",
                "country": "MK",
            },
        ]

        result = synthesize_cluster_fallback(articles, lang="mk")

        # 1. First detail sentence should be from the first/highest scoring sentence
        assert "Vladata donese odluka za zamrznuvanje" in result["summary"]

        # 2. In generated_article, we should have a fusion of the distinct sentences
        assert "Vladata donese odluka za zamrznuvanje" in result["generated_article"]
        assert "Graganite ja pozdravija novata odluka" in result["generated_article"]

        # 3. The duplicate sentence should not be repeated
        text_lower = result["generated_article"].lower()
        assert text_lower.count("zamrznuvanje na cenite") == 1

    def test_synthesize_cluster_fallback_does_not_insert_sports_context_for_economy(self):
        from nlp.generation import synthesize_cluster_fallback

        articles = [
            {
                "source": "Kurir.mk",
                "title": "Девизните резерви 5,2 милијарди евра",
                "description": (
                    "Девизни резерви на крајот на април годинава изнесувале 5.207 милиони евра. "
                    "Најголем дел се пласирани во хартии од вредност."
                ),
                "category": "Makedonija",
                "topic": "Ekonomija",
                "country": "MK",
            },
            {
                "source": "Nezavisen.mk",
                "title": "Девизните резерви 5,2 милијарди евра",
                "description": "Податоците на Народната банка покажуваат раст на резервите.",
                "category": "Makedonija",
                "topic": "Ekonomija",
                "country": "MK",
            },
        ]

        result = synthesize_cluster_fallback(articles, lang="mk")

        assert "Спортското значење" not in result["generated_article"]
        assert "резерв" in result["generated_article"].lower()



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
        result = rewrite_to_serbian_locally("Prime Minister announced new measures on Tuesday according to officials")

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

        assert "120 milioni evra" in result["summary"]
        assert "приказната ја следат 2 извори" in result["summary"].lower()

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
        assert any(p["angle"] == "Нијанси" for p in result["perspectives"])
        assert any(p["angle"] == "отворено" for p in result["perspectives"])


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

        assert "## Големата Слика" in result
        assert "## Клучни теми" in result
        assert "- Клучен аспект:" in result or "- Зошто е важно:" in result

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

        assert "Sobraniskata rasprava za interpelacijata vleguva vo zavrsna faza" in result
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

        intro_line = next(line for line in result.splitlines() if "Bugarija" in line or "Zemjotres" in line)
        assert "Bugarija danas izleguva na parlamentarni izbori" in intro_line
        assert "SDSM: Vo ocajna potraga po dobra vest" not in intro_line

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

        assert "## Клучни теми" in result
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

        assert "Големата Слика" in result
        assert "Клучни теми" in result

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

        assert "Големата Слика" in result
        assert "Bugarija" in result or "izbori" in result

    def test_generate_daily_brief_fallback_sr_intro_uses_titles_not_broken_sentences(self):
        clusters = [
            {
                "title": "DS zahteva reakciju nadležnih: Nadgrobni spomenik Zoranu Đinđiću oštećen",
                "source": "Blic",
                "topic": "Politika",
                "description": "Demokratska stranka zatražila je danas od organa da identifikuju vandale.",
                "source_count": 2,
            },
            {
                "title": "Masovna pucnjava u Teksasu, jedna osoba poginula",
                "source": "Reuters",
                "topic": "Svet",
                "description": "Oko deset ljudi ranjeno je u pucnjavi u zapadnom Teksasu.",
                "source_count": 3,
            },
        ]

        result = generate_daily_brief_fallback(clusters, lang="sr")

        assert "Dan je obeležio Demokratska stranka" not in result
        assert "Danas se izdvajaju dve teme:" in result
        assert "Urednički pregled baziran na 5 izvora." in result

    def test_generate_daily_brief_fallback_sr_avoids_incomplete_key_aspect(self):
        clusters = [
            {
                "title": "Dvoje srpskih državljana poginulo u saobraćajnim nesrećama u Crnoj Gori",
                "source": "Beta",
                "topic": "Region",
                "description": "Motociklista iz Srbije M.J. poginuo je danas u saobraćajnoj nesreći na putu između Žabljaka i Šavnika.",
                "source_count": 2,
            }
        ]

        result = generate_daily_brief_fallback(clusters, lang="sr")
        key_aspect_lines = [line for line in result.splitlines() if line.startswith("- Ključni aspekt:")]

        assert key_aspect_lines
        assert all("poginuo je danas" in line for line in key_aspect_lines)
        assert "Događaj je u fazi razvoja" not in result

    def test_generate_daily_brief_fallback_sr_watch_signals_are_not_all_identical(self):
        clusters = [
            {
                "title": "Nemačka propustila rok EU – preti joj kazna",
                "source": "DW",
                "topic": "Evropa",
                "description": "Nemačka nije uspela da unese direktivu o transparentnosti plata u rok.",
                "source_count": 4,
            },
            {
                "title": "Masovna pucnjava u Teksasu",
                "source": "AP",
                "topic": "Svet",
                "description": "Policija istražuje okolnosti pucnjave.",
                "source_count": 2,
            },
        ]

        result = generate_daily_brief_fallback(clusters, lang="sr")
        watch_section = result.split("## Šta pratiti", 1)[1].split("**Beleška**", 1)[0]
        watch_lines = [line.strip() for line in watch_section.splitlines() if line.strip().startswith("- ")]

        assert len(watch_lines) == 2
        assert watch_lines[0] != watch_lines[1]
        assert "Sledeći signal biće da li će zvanični akteri" not in watch_lines[0]

    def test_generate_daily_brief_fallback_sr_avoids_mechanical_editorial_phrases(self):
        clusters = [
            {
                "title": "Nemačka propustila rok EU - preti joj kazna",
                "source": "DW",
                "topic": "Evropa",
                "description": "Nemačka nije uspela da unese direktivu o transparentnosti plata u rok.",
                "source_count": 4,
            },
            {
                "title": "Masovna pucnjava u Teksasu",
                "source": "AP",
                "topic": "Svet",
                "description": "Policija istražuje okolnosti pucnjave.",
                "source_count": 2,
            },
        ]

        result = generate_daily_brief_fallback(clusters, lang="sr")

        assert "Danas se izdvajaju dve teme:" in result
        assert "Današnji pregled vodi priča" not in result
        assert "Potvrđen razvoj sa visokim medijskim konsenzusom" not in result
        assert "Pratiti da li će se narativ" not in result

    def test_generate_daily_brief_fallback_mk_avoids_mechanical_editorial_phrases(self):
        clusters = [
            {
                "title": "Германија го пропушти рокот на ЕУ - и се заканува казна",
                "source": "DW",
                "topic": "Европа",
                "description": "Германија не успеа навреме да ја внесе директивата за транспарентност на платите.",
                "source_count": 4,
            },
            {
                "title": "Масовно пукање во Тексас",
                "source": "AP",
                "topic": "Свет",
                "description": "Полицијата ги истражува околностите на пукањето.",
                "source_count": 2,
            },
        ]

        result = generate_daily_brief_fallback(clusters, lang="mk")

        assert "Денес се издвојуваат две теми:" in result
        assert "Следниот сигнал е официјална потврда или нова бројка" in result
        assert "Денешниот преглед ја води приказната" not in result
        assert "Потврден развој со висок медиумски консензус" not in result
        assert "Следете дали наративот" not in result


# =============================================================================
# Gold Standard Test Cases for NLP Quality
# These test cases establish expected behavior for NLP operations
# =============================================================================


class TestGoldStandardTagFiltering:
    """Gold standard tests for tag filtering quality."""

    def test_filter_rejects_time_markers(self):
        """Gold standard: Time markers should be filtered out."""
        tags = ["15:30", "dnes", "Makedonija"]
        filtered = filter_cluster_tags(tags)
        assert "15:30" not in filtered
        assert "dnes" not in filtered
        assert "Makedonija" in filtered

    def test_filter_preserves_entities(self):
        """Gold standard: Real entities should survive filtering."""
        tags = ["Poveće", "Kako", "Makedonija", "Evropa"]
        filtered = filter_cluster_tags(tags)
        assert "Makedonija" in filtered
        assert "Evropa" in filtered


class TestGoldStandardEntityRecognition:
    """Gold standard tests for entity recognition in clustering."""

    def test_entities_prioritized_over_generic_terms(self):
        """Gold standard: Proper nouns and entities should rank higher than generic terms."""
        titles = [
            "Pretsedatelot na Makedonija se sastal so pretsedatelot na Albanska",
        ]
        entities = [
            {"entity_name": "Makedonija", "entity_type": "country"},
            {"entity_name": "Albanska", "entity_type": "country"},
        ]

        tags = extract_cluster_tags_locally(titles, entity_names=entities, top_n=5)
        assert "Makedonija" in tags
        assert "Albanska" in tags


class TestGoldStandardKeyphraseExtraction:
    """Gold standard tests for keyphrase extraction quality."""

    def test_extract_keyphrases_ignores_agency_attribution(self):
        """Gold standard: Agency names should not be keyphrases."""
        text = "MIA soopštava deka Vladata usvoi nov paket mera. Reuters pisuva deka merkite ke pocnat."
        phrases = extract_keyphrases_locally(text, top_n=10)
        phrase_text = " ".join(phrases).lower()
        assert "mia" not in phrase_text
        assert "reuters" not in phrase_text
        assert "paket" in phrase_text or "mera" in phrase_text or "vlada" in phrase_text
