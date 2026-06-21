from tasks.intelligence.synthesis import _evaluate_synthesis_candidate


def test_golden_sr_candidate_passes_quality_and_copy_gates():
    article_rows = [
        {
            "title": "Vlada usvojila izmene zakona",
            "description": "Parlament je doneo izmene.",
            "source": "RTS",
        }
    ]
    res_data = {
        "synthetic_headline": "Vlada usvojila izmene zakona o pravosuđu",
        "summary": (
            "- Šta se desilo: Vlada je usvojila izmene.\n"
            "- Zašto je važno: Menja se okvir rada sudova.\n"
            "- Šta je potvrđeno: RTS i Blic navode iste izmene.\n"
            "- Šta ostaje otvoreno: Rok primene."
        ),
        "article": (
            "Vlada Srbije je usvojila paket izmena zakona o pravosuđu nakon javne rasprave.\n\n"
            "Izmene obuhvataju procedure imenovanja sudija i rokove odlučivanja.\n\n"
            "Analitičari ističu da je ključno kako će se primenjivati nova pravila.\n\n"
            "Izvori se razlikuju oko roka primene, ali potvrđuju osnovne izmene.\n\n"
            "Ostaje otvoreno da li će opozicija podržati dalje korake u proceduri."
        ),
        "key_facts": [
            "RTS: Vlada usvojila izmene",
            "Blic: Izmene zakona",
            "Analiza: rok primene",
            "Otvoreno: procedura",
        ],
    }

    evaluated, fail_reason, _ = _evaluate_synthesis_candidate(
        res_data,
        provider="nvidia",
        article_rows=article_rows,
        lang="sr",
        fast_mode=False,
        current_context="Vlada usvojila izmene zakona",
        legacy_summary="",
    )
    assert evaluated is not None
    assert fail_reason is None
    assert evaluated["quality_score"] >= 0.7


def test_golden_sr_candidate_rejects_cyrillic_leak():
    article_rows = [{"title": "Vlada", "description": "Izmene", "source": "RTS"}]
    res_data = {
        "synthetic_headline": "Влада Србије усвојила измене",
        "summary": "- Šta: измене\n- Važno: правосуђе\n- Potvrđeno: извори\n- Otvoreno: рок",
        "article": (
            "Влада Србије је данас усвојила измене закона о правосуђу.\n\n"
            "Измене обухватају процедуре именовања судија.\n\n"
            "Аналитичари истичу да је кључно како ће се примењивати нова правила.\n\n"
            "Извори се разликују око рока primene.\n\n"
            "Остаје отворено да ли ће опозиција подржати даље кораке."
        ),
        "key_facts": ["RTS: izmene", "Blic: zakon", "Analiza: rok", "Otvoreno: procedura"],
    }

    evaluated, fail_reason, diagnostics = _evaluate_synthesis_candidate(
        res_data,
        provider="nvidia",
        article_rows=article_rows,
        lang="sr",
        fast_mode=True,
        current_context="Vlada izmene",
        legacy_summary="",
    )
    assert evaluated is None
    assert fail_reason == "sr_copy_purity_failed"
    assert diagnostics is not None


def test_golden_mk_candidate_rejects_latin_leak():
    article_rows = [
        {
            "title": "Холандија",
            "description": "Натпревар резултат 2:2",
            "source": "МРТ",
        }
    ]
    res_data = {
        "synthetic_headline": "Холандија и Јапонија",
        "summary": "- Развој: vo meč rezultatot beše 2:2\n- Важно: натпреварот\n- Потврдено: извори\n- Отворено: ништо",
        "article": (
            "Vo meč pomeđu Holandija i Japonija rezultatot beše 2:2.\n\n"
            "Vo vtoro poluvreme se odvijaše intenziven fudbal.\n\n"
            "Izvori potvrduvaat rezultat.\n\n"
            "Ostava nejasno ko ke napreduva.\n\n"
            "Klubovi komentiraat nastap."
        ),
        "key_facts": ["MRT: 2:2", "A1: poluvreme", "Sport: fudbal", "Analiza: neresen"],
    }

    evaluated, fail_reason, diagnostics = _evaluate_synthesis_candidate(
        res_data,
        provider="nvidia",
        article_rows=article_rows,
        lang="mk",
        fast_mode=True,
        current_context="Холандија Јапонија",
        legacy_summary="",
    )
    assert evaluated is None
    assert fail_reason == "mk_copy_purity_failed"
    assert diagnostics is not None


def test_golden_sr_candidate_rejects_ungrounded_numbers():
    article_rows = [{"title": "Vlada", "description": "Bez brojeva", "source": "RTS"}]
    res_data = {
        "synthetic_headline": "Vlada usvojila izmene",
        "summary": "- Šta: izmene\n- Važno: zakon\n- Potvrđeno: izvori\n- Otvoreno: rok",
        "article": (
            "Vlada je usvojila izmene za 9876 izvora, 5432 posto podrske i 1111 amandmana.\n\n"
            "Izmene obuhvataju procedure imenovanja sudija.\n\n"
            "Analiticari isticu da je kljucno kako ce se primenjivati nova pravila.\n\n"
            "Izvori se razlikuju oko roka primene.\n\n"
            "Ostaje otvoreno da li ce opozicija podrzati dalje korake."
        ),
        "key_facts": ["RTS: izmene", "Blic: zakon", "Analiza: rok", "Otvoreno: procedura"],
    }

    evaluated, fail_reason, _ = _evaluate_synthesis_candidate(
        res_data,
        provider="nvidia",
        article_rows=article_rows,
        lang="sr",
        fast_mode=False,
        current_context="Vlada izmene",
        legacy_summary="",
    )
    assert evaluated is None
    assert fail_reason == "fact_grounding_failed"


def test_golden_mk_candidate_passes_clean_cyrillic():
    article_rows = [
        {
            "title": "Холандија победи",
            "description": "Натпревар заврши 2:0",
            "source": "МРТ",
        }
    ]
    res_data = {
        "synthetic_headline": "Холандија со убедлива победа",
        "summary": "- Развој: победа 2:0\n- Важно: натпреварот\n- Потврдено: извори\n- Отворено: ништо",
        "article": (
            "Холандија оствари победа од 2:0 во натпреварот според извештаите на МРТ.\n\n"
            "Вториот дел беше поинтензивен од првиот.\n\n"
            "Изворите потврдуваат резултатот.\n\n"
            "Останува нејасно кој ќе напредува понатаму.\n\n"
            "Клубовите го коментираа настапот."
        ),
        "key_facts": ["MRT: 2:0", "A1: победа", "Sport: фудбал", "Analiza: нерешено"],
    }

    evaluated, fail_reason, _ = _evaluate_synthesis_candidate(
        res_data,
        provider="nvidia",
        article_rows=article_rows,
        lang="mk",
        fast_mode=True,
        current_context="Холандија",
        legacy_summary="",
    )
    assert evaluated is not None
    assert fail_reason is None


def test_golden_fast_mode_skips_hallucination_gate():
    article_rows = [{"title": "Vlada", "description": "Izmene", "source": "RTS"}]
    res_data = {
        "synthetic_headline": "Vlada usvojila izmene",
        "summary": "- Šta: izmene\n- Važno: zakon\n- Potvrđeno: izvori\n- Otvoreno: rok",
        "article": (
            "Vlada Srbije je usvojila paket izmena zakona o pravosudju.\n\n"
            "Izmene obuhvataju procedure imenovanja sudija.\n\n"
            "Analiticari isticu da je kljucno kako ce se primenjivati nova pravila.\n\n"
            "Izvori se razlikuju oko roka primene.\n\n"
            "Ostaje otvoreno da li ce opozicija podrzati dalje korake."
        ),
        "key_facts": ["RTS: izmene", "Blic: zakon", "Analiza: rok", "Otvoreno: procedura"],
    }

    evaluated, fail_reason, _ = _evaluate_synthesis_candidate(
        res_data,
        provider="nvidia",
        article_rows=article_rows,
        lang="sr",
        fast_mode=True,
        current_context="Potpuno drugaciji kontekst koji nije u tekstu",
        legacy_summary="",
    )
    assert evaluated is not None
    assert fail_reason is None
