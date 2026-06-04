from tasks.intelligence import (
    _clean_macedonian_spelling_and_script,
    _is_grounded_synthesis,
    _score_editorial_summary,
    _score_synthesis_quality,
)
from nlp.generation import synthesize_cluster_fallback

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
