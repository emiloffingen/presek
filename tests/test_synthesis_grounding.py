from tasks.intelligence.synthesis_grounding import (
    _fact_grounding_diagnostics,
    _is_grounded_synthesis,
)


def test_fact_grounding_allows_grounded_numbers():
    article_rows = [
        {
            "title": "Vlada usvojila izmene",
            "description": "Parlament je doneo izmene u 2026.",
            "source": "RTS",
        }
    ]
    text = "Vlada je usvojila izmene nakon rasprave u 2026."
    diag = _fact_grounding_diagnostics(text, article_rows, "sr", fast_mode=False)
    assert diag["ok"] is True


def test_fact_grounding_flags_ungrounded_numbers():
    article_rows = [{"title": "Vlada", "description": "Bez brojeva", "source": "RTS"}]
    text = "Vlada je usvojila izmene za 9876 izvora, 5432 posto podrske i 1111 amandmana."
    diag = _fact_grounding_diagnostics(text, article_rows, "sr", fast_mode=False)
    assert diag["ok"] is False
    assert diag["ungrounded_numbers"]


def test_entity_grounding_rejects_hallucinated_name():
    source = "Vlada Srbije je usvojila izmene zakona."
    synthesis = "Vlada Srbije i Milan Nepoznati su usvojili izmene zakona."
    assert _is_grounded_synthesis(synthesis, source) is False


def test_entity_grounding_accepts_source_entities():
    source = "Vlada Srbije je usvojila izmene zakona."
    synthesis = "Vlada Srbije je usvojila paket izmena nakon javne rasprave."
    assert _is_grounded_synthesis(synthesis, source) is True
