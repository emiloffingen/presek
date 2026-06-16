from tasks.intelligence.synthesis_prompt import (
    _build_cluster_synthesis_content,
    _build_cluster_synthesis_prompt,
    _order_synthesis_langs,
)


def test_order_synthesis_langs_puts_serbian_first_for_bilingual():
    assert _order_synthesis_langs(["mk", "sr"]) == ["sr", "mk"]
    assert _order_synthesis_langs(["sr"]) == ["sr"]


def test_build_cluster_synthesis_content_lists_sources():
    rows = [
        {"source": "RTS", "title": "Vlada doneo izmene"},
        {"source": "Blic", "title": "Parlament glasa"},
    ]
    content = _build_cluster_synthesis_content(rows)
    assert "[RTS]" in content
    assert "Vlada doneo izmene" in content


def test_build_cluster_synthesis_prompt_includes_editorial_focus():
    prompt = _build_cluster_synthesis_prompt(
        [{"source": "RTS", "title": "Vest", "description": "Opis"}],
        lang="sr",
    )
    assert "<articles_context>" in prompt
    assert "UREĐIVAČKI FOKUS" in prompt
