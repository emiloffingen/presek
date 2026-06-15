from tasks.intelligence import (
    _build_source_comparison_prompt_block,
    _clean_macedonian_spelling_and_script,
    _is_fact_grounded_synthesis,
    _is_grounded_synthesis,
    _score_editorial_summary,
    _score_synthesis_quality,
)
from nlp.generation import synthesize_cluster_fallback
from tasks.synthesis_sanitize import sanitize_synthesis_outputs

def test_clean_macedonian_spelling_and_script():
    # Test lookalike/homoglyph swap
    # In 'акциjа', the 'j' is Latin
    assert _clean_macedonian_spelling_and_script("акциjа") == "акција"
    
    # Test Serbian leak word mappings
    assert _clean_macedonian_spelling_and_script("Током состанокот") == "Во текот на состанокот"
    assert _clean_macedonian_spelling_and_script("премијер") == "премиер"
    assert _clean_macedonian_spelling_and_script("између") == "меѓу"
    
    # Test Latin transliteration
    assert _clean_macedonian_spelling_and_script("sostanok") == "состанок"
    
    # Test HTML and citation exemption
    assert _clean_macedonian_spelling_and_script("[1] vest") == "[1] вест"
    assert _clean_macedonian_spelling_and_script("NATO и EU") == "NATO и EU"

def test_score_synthesis_quality():
    # Good synthesis
    headline = "Novi predsednik preuzeo dužnost"
    article = "Prvi pasus o preuzimanju dužnosti.\n\nDrugi pasus o ceremoniji.\n\nTreći pasus o dogovoru medija [1].\n\nČetvrti pasus o tome gde se razlikuju [2].\n\nPeti pasus o neverifikovanom razvoju i otvoreno pitanje?"
    key_facts = ["Fact 1", "Fact 2", "Fact 3", "Fact 4"]
    score = _score_synthesis_quality(headline, article, key_facts)
    assert score == 1.0

    # Low score: Headline repeated
    headline = "Novi predsednik preuzeo dužnost"
    article = "Novi predsednik preuzeo dužnost.\n\nDrugi pasus.\n\nTreći pasus [1].\n\nČetvrti pasus [2].\n\nPeti pasus?"
    score = _score_synthesis_quality(headline, article, key_facts)
    assert score < 1.0

    # Low score: Fewer than 4 citations/facts
    headline = "Novi predsednik"
    article = "Prvi pasus.\n\nDrugi pasus.\n\nTreći pasus.\n\nČetvrti pasus.\n\nPeti pasus?"
    score = _score_synthesis_quality(headline, article, [])
    assert score < 1.0

    # Low score: Broken paragraph structure
    headline = "Novi predsednik"
    article = "Prvi pasus.\n\nDrugi pasus."
    score = _score_synthesis_quality(headline, article, key_facts)
    assert score < 1.0


def test_score_synthesis_quality_penalizes_unsupported_abstraction():
    headline = "Požar zatvorio tržni centar"
    article = (
        "Požar je izbio u tržnom centru i vatrogasci su evakuisali posetioce.\n\n"
        "Incident je otvorio pitanje bezbednosnih procedura u objektu.\n\n"
        "Izvori potvrđuju lokaciju i intervenciju [1].\n\n"
        "Nije potvrđeno šta je izazvalo požar [2].\n\n"
        "Požar postaje simbol šire neizvesnosti i legitimnost institucija ostaje centralno pitanje?"
    )
    key_facts = ["Požar", "Tržni centar", "Evakuacija", "Istraga"]

    assert _score_synthesis_quality(headline, article, key_facts) < 0.85


def test_sanitize_synthesis_outputs_normalizes_serbian_copy():
    summary, article, perspectives = sanitize_synthesis_outputs(
        ["Izvještaj navodi da su njive izgorjele."],
        (
            "Izvještaj o događaju navodi da su njive izgorjele posle požara.\n\n"
            "Narativa nema dovoljno, ali osnovne činjenice su potvrđene u više izvora."
        ),
        [{"angle": "Celosno", "content": "Izvještaj ostaje otvoren."}],
        [{"title": "Požar", "description": "Njive su izgorele."}],
        lang="sr",
    )

    assert summary == "• izveštaj navodi da su njive izgorele."
    assert "izveštaj" in article
    assert "narativ" in article
    assert perspectives[0]["angle"] == "Celo"


def test_score_editorial_summary_prefers_distinct_editorial_bullets():
    good = [
        "Vlada je usvojila novi predlog posle pregovora sa sindikatima, čime je promenjen prvobitni plan isplate.",
        "Ulog je budžetski i politički, jer odluka direktno utiče na javni sektor i naredne pregovore.",
        "Više izvora potvrđuje osnovnu odluku, dok se razlikuju u proceni ko je napravio ključni ustupak.",
        "Otvoreno ostaje kada će mere biti sprovedene i da li će ih potvrditi nadležne institucije.",
    ]
    weak = [
        "Razvoj događaja privukao je pažnju javnosti.",
        "Izvori izveštavaju o razvoju događaja.",
        "Situacija ostaje dinamična u širem kontekstu.",
    ]

    assert _score_editorial_summary(good, "") >= 0.8
    assert _score_editorial_summary(weak, "") < 0.7


def test_fallback_synthesis_summary_is_editorial_not_labelled():
    articles = [
        {
            "title": "Vlada usvojila predlog o povećanju plata u javnom sektoru",
            "description": "Vlada je usvojila predlog posle sastanka sa sindikatima. Izvori navode da će odluka uticati na budžet i pregovore o narednoj godini.",
            "source": "Izvor A",
            "country": "RS",
            "category": "Srbija",
            "topic": "Politika",
        },
        {
            "title": "Sindikati traže garancije za rokove isplate",
            "description": "Sindikati potvrđuju dogovor, ali traže precizne rokove isplate. Nije jasno kada će mere stupiti na snagu.",
            "source": "Izvor B",
            "country": "RS",
            "category": "Srbija",
            "topic": "Politika",
        },
    ]

    result = synthesize_cluster_fallback(articles, lang="sr")
    summary = result["summary"]

    assert "Ključni razvoj:" not in summary
    assert "Pokrivenost:" not in summary
    assert _score_editorial_summary(summary, result["generated_article"], "sr") >= 0.6


def test_hallucination_gate_allows_role_prefixed_grounded_names():
    source = """
    [1] RTS
    Naslov: Aleksandar Vučić razgovarao je sa predstavnicima vlade u Beogradu.
    Opis: Vučić je najavio da će odluka biti predstavljena nakon sednice.
    """
    synthesis = (
        "Serbian President Aleksandar Vučić razgovarao je sa predstavnicima vlade u Beogradu.\n\n"
        "Izvori potvrđuju sastanak, dok rokovi za odluku ostaju nejasni."
    )

    assert _is_grounded_synthesis(synthesis, source)


def test_hallucination_gate_rejects_ungrounded_multiword_entities():
    source = """
    [1] Lokalni izvor
    Naslov: Vlada raspravlja o budžetu i platama u javnom sektoru.
    Opis: Sindikati traže rokove isplate, ali nema pomena stranih zvaničnika.
    """
    synthesis = (
        "President Donald Trump i West Virginia postali su deo pregovora o platama.\n\n"
        "Odluka se predstavlja kao međunarodni pritisak, iako izvori to ne pominju."
    )

    assert not _is_grounded_synthesis(synthesis, source)


def test_fact_gate_rejects_ungrounded_numbers():
    articles = [
        {
            "title": "Vlada usvojila predlog o platama",
            "description": "Dogovor sa sindikatima pokriva 12.000 zaposlenih u javnom sektoru.",
            "source": "Izvor A",
        }
    ]
    grounded = "Vlada je usvojila predlog koji pokriva 12.000 zaposlenih u javnom sektoru."
    borderline = "Vlada je usvojila predlog koji pokriva 12.000 zaposlenih i planira dodatnih 500 mesta."
    hallucinated = (
        "Vlada je usvojila predlog koji pokriva 45.000 zaposlenih, budžet od 2,3 milijarde, "
        "88% rasta i 500 novih radnih mesta van izvora."
    )

    assert _is_fact_grounded_synthesis(grounded, articles, lang="sr")
    assert _is_fact_grounded_synthesis(borderline, articles, lang="sr")
    assert not _is_fact_grounded_synthesis(hallucinated, articles, lang="sr")


def test_fact_gate_treats_thousand_separator_variants_as_grounded():
    articles = [
        {
            "title": "Plata",
            "description": "Reforma pokriva 12.000 zaposlenih.",
            "source": "Izvor A",
        }
    ]
    synthesis = "Reforma pokriva 12000 zaposlenih prema izvorima."
    assert _is_fact_grounded_synthesis(synthesis, articles, lang="sr")


def test_source_comparison_prompt_block_includes_local_analysis():
    articles = [
        {
            "title": "Vlada usvojila predlog o platama",
            "description": "Sindikati traže rokove isplate.",
            "source": "Izvor A",
        },
        {
            "title": "Sindikati traže garancije",
            "description": "Nije jasno kada mere stupaju na snagu.",
            "source": "Izvor B",
        },
    ]

    block = _build_source_comparison_prompt_block(articles, lang="sr")
    assert "<source_comparison>" in block
    assert len(block) > 80
