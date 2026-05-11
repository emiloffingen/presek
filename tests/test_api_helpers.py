from api_helpers import (
    normalize_citation_sources,
    normalize_perspectives,
    normalize_summary_text,
)


def test_normalize_summary_text_dedupes_and_strips_noise():
    raw = """
    clanci:
    • Glaven razvoj: Tramp: Utorak, 20:00 casot po istocno vreme
    • Glaven razvoj: Tramp: Utorak, 20:00 casot po istocno vreme
    kontekst: Amerikanskiot pretsedatel najavi vazno obracanje.
    """

    result = normalize_summary_text(raw)

    assert "clanci" not in result
    assert result.count("Glaven razvoj") == 1
    assert "Amerikanskiot pretsedatel" in result


def test_normalize_perspectives_infers_angles_and_dedupes():
    raw = [
        "Poveceto izvori se vrtat okolu carinite i rokot za obracanje.",
        {
            "angle": "perspektiva",
            "content": "Poveceto izvori se vrtat okolu carinite i rokot za obracanje.",
        },
        {
            "label": "perspektiva",
            "text": "Razlikite najmnogu se vo akcentot i formulacijata.",
        },
        {
            "angle": "",
            "content": "ostaje nejasno dali merkite ce stapat vednas na sila.",
        },
    ]

    result = normalize_perspectives(raw)

    assert len(result) == 3
    assert result[0]["angle"] == "Zajednicka linija"
    assert result[1]["angle"] == "Razliciti akcenti"
    assert result[2]["angle"] == "Sta ostaje otvoreno"


def test_normalize_citation_sources_orders_and_cleans_rows():
    raw = [
        {
            "source": " MIA ",
            "title": " Naslov ",
            "link": "https://example.com/1",
            "created_at": "2026-04-05T12:00:00",
            "category": " Svet ",
        },
        {"source": "DW", "title": "Vtor naslov", "link": "https://example.com/2"},
    ]

    result = normalize_citation_sources(raw)

    assert [item["index"] for item in result] == [1, 2]
    assert result[0]["source"] == "MIA"
    assert result[0]["title"] == "Naslov"
    assert result[0]["category"] == "Svet"
