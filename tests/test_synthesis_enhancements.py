from tasks.intelligence import _clean_macedonian_spelling_and_script, _score_synthesis_quality

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
