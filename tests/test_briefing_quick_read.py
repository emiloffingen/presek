from core.briefing_quick_read import build_quick_read_payload


def test_build_quick_read_extracts_bullets_and_narratives():
    content = """# Dnevni brifing

Uvod u dan.

- Prva kljucna vest sa vise izvora
- Druga razvojna linija u regionu
- Treca tema za pracenje tokom dana
"""
    metadata = {
        "key_narratives": [{"text": "Mediji se slazu oko jezgra.", "sentiment": "NEUTRALAN"}],
        "stats": {"total_articles": 120, "intl_share": 18, "pluralism_score": 42},
    }

    payload = build_quick_read_payload(content, metadata, lang="sr")

    assert payload["read_minutes"] >= 3
    assert len(payload["bullets"]) == 3
    assert payload["bullets"][0].startswith("Prva")
    assert payload["narratives"][0]["text"].startswith("Mediji")
    assert payload["stats"]["total_articles"] == 120


def test_build_quick_read_mk_copy():
    payload = build_quick_read_payload("", {}, lang="mk")
    assert payload["headline"] == "5-минутно читање"
