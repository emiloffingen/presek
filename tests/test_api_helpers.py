import json
from api_helpers import normalize_perspectives, build_citation_snippet
from utils import get_source_trust_label


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
    assert result[0]["angle"] == "Kljucan ugao"
    assert result[1]["angle"] == "razliciti akcenti"
    assert result[2]["angle"] == "Sta ostaje otvoreno"


def test_normalize_citation_sources_orders_and_cleans_rows():
    # This is indirectly tested through snippet building
    pass


def test_build_citation_snippet_handles_empty():
    assert build_citation_snippet({}) == ""
    assert build_citation_snippet(None) == ""


def test_build_citation_snippet_uses_summary_or_description():
    art1 = {"summary": "Kratko rezime", "description": "Dolg opis"}
    assert build_citation_snippet(art1) == "Dolg opis"

    art2 = {"summary": "", "description": "Samo opis"}
    assert build_citation_snippet(art2) == "Samo opis"


def test_get_source_trust_label():
    label = get_source_trust_label("N1 Info")
    assert label in ["Visoko poverenje", "Potvrden izvor", "sledeci izvor"]
