from nlp.generation import generate_local_placeholder
from nlp.placeholder_brand import PRESEK_MARK_LIGHT, category_palette, minimal_fallback_svg


def test_category_palette_uses_warm_presek_mark_for_srbija():
    bg, spot, accent = category_palette("Srbija", light=True)
    assert bg == "#fbfaf5"
    assert accent == PRESEK_MARK_LIGHT


def test_generate_local_placeholder_uses_warm_paper_background():
    svg = generate_local_placeholder("abc123", "Test headline", "Srbija", theme="light")
    assert "stop-color: #fbfaf5;" in svg
    assert "stop-color: #ece8df;" in svg
    assert PRESEK_MARK_LIGHT in svg
    assert "#1e40af" not in svg
    assert "#8b5cf6" not in svg


def test_generate_local_placeholder_includes_brand_cut_bar():
    svg = generate_local_placeholder("abc123", "Test headline", "vesti", theme="dark")
    assert 'width="5" height="370"' in svg
    assert "ph-accent-fill" in svg


def test_minimal_fallback_svg_uses_presek_mark():
    svg = minimal_fallback_svg(lang="sr")
    assert PRESEK_MARK_LIGHT in svg
    assert "#27272a" not in svg
