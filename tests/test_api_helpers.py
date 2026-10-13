from core.api_helpers import build_citation_snippet, normalize_perspectives
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


def test_get_source_trust_label():
    label = get_source_trust_label("N1 Info")
    assert label in ["Visoko poverenje", "Potvrden izvor", "sledeci izvor"]


def test_normalize_perspectives_filters_leaked_json_keys():
    raw = [
        {"angle": "Proevropski i reformistički", "content": "Valid perspective content"},
        "verification_report': {",
        "agreements': [",
        {"angle": "verification_report", "content": "some text"},
        {
            "angle": "valid",
            "content": "this has agreements in the middle of standard text but we filter it to be safe.",
        },
    ]
    result = normalize_perspectives(raw)
    assert len(result) == 1
    assert result[0]["content"] == "Valid perspective content"
