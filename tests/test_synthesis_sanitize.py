from tasks.synthesis_sanitize import sanitize_synthesis_outputs, sanitize_text_field


def test_sanitize_text_field_unwraps_json_summary():
    leaked = '{"summary":"Cisto rezime iz AI sloja"}'
    assert sanitize_text_field(leaked) == "Cisto rezime iz AI sloja"


def test_sanitize_synthesis_outputs_replaces_leaked_summary():
    article_rows = [{"title": "Naslov", "description": "Opis", "source": "A"}]
    summary, article, perspectives = sanitize_synthesis_outputs(
        '{"summary":"Prvi pasus"}',
        "Validan clanak sa vise od osamdeset karaktera koji opisuje dogadjaj bez JSON curenja.",
        [],
        article_rows,
        lang="sr",
    )
    assert "Prvi pasus" in summary
    assert "{" not in summary
    assert isinstance(perspectives, list)
