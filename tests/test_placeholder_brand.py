import xml.dom.minidom

from nlp.generation import generate_local_placeholder
from nlp.placeholder_brand import PRESEK_MARK_DARK, PRESEK_MARK_LIGHT, category_palette


def test_placeholder_is_valid_svg_in_both_themes():
    for theme in (None, "dark"):
        svg = generate_local_placeholder("c1", "Наслов", "Sport", theme=theme, lang="mk")
        xml.dom.minidom.parseString(svg)


def test_placeholder_does_not_repeat_the_headline():
    svg = generate_local_placeholder("c1", "Многу специфичен наслов на вест", "Makedonija", lang="mk")
    assert "специфичен" not in svg


def test_placeholder_escapes_category():
    svg = generate_local_placeholder("c1", "t", "<script>", lang="sr")
    xml.dom.minidom.parseString(svg)
    assert "<script>" not in svg


def test_unknown_section_falls_back_to_brand_accent():
    assert category_palette("default", light=True)[2] == PRESEK_MARK_LIGHT
    assert category_palette("default", light=False)[2] == PRESEK_MARK_DARK
    assert category_palette("no-such-key", light=True)[2] == PRESEK_MARK_LIGHT
