from tasks.intelligence.synthesis_bundle import (
    _build_citation_sources,
    _build_synthesis_source_context,
    _fallback_key_facts,
)


def test_fallback_key_facts_dedupes_sources():
    rows = [
        {"source": "RTS", "title": "Vlada doneo izmene"},
        {"source": "RTS", "title": "Vlada doneo izmene"},
        {"source": "Blic", "title": "Parlament glasa"},
    ]
    facts = _fallback_key_facts(rows, limit=4)
    assert len(facts) == 2
    assert any("RTS" in fact for fact in facts)


def test_build_citation_sources_preserves_order():
    rows = [
        {"source": "RTS", "title": "A", "link": "https://rts.rs/a"},
        {"source": "Blic", "title": "B", "link": "https://blic.rs/b"},
    ]
    citations = _build_citation_sources(rows)
    assert citations[0]["source"] == "RTS"
    assert citations[1]["source"] == "Blic"


def test_build_synthesis_source_context_includes_header_and_sources():
    rows = [
        {
            "source": "RTS",
            "title": "Vlada doneo izmene",
            "description": "Parlament je doneo izmene zakona.",
            "category": "Politika",
            "topic": "Politika",
        }
    ]
    context = _build_synthesis_source_context(rows, lang="sr")
    assert "Dostupno je" in context
    assert "RTS" in context
    assert "Naslov" in context
