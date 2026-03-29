import pytest
from ingestion import normalize_headline, clean_rss_footer

def test_normalize_headline():
    assert normalize_headline("ВИДЕО: Ова е наслов") == "Ова е наслов"
    assert normalize_headline("Нормален наслов") == "Нормален наслов"
    assert normalize_headline("  Ова е наслов со празни места  ") == "Ова е наслов со празни места"
    assert normalize_headline("") == ""

def test_clean_rss_footer():
    text1 = "This is some news content. The post Some title appeared first on Some source."
    assert clean_rss_footer(text1) == "This is some news content."
    
    text2 = "Content. This article was originally published on Site."
    assert clean_rss_footer(text2) == "Content."
    
    text3 = "News text. Source: https://example.com"
    assert clean_rss_footer(text3) == "News text."

    text4 = "Just normal news text without any footer."
    assert clean_rss_footer(text4) == text4


def test_clean_rss_footer_macedonian():
    text = "Содржина на вестта. Прочитајте повеќе на example.com"
    assert clean_rss_footer(text) == "Содржина на вестта."


def test_clean_rss_footer_empty():
    assert clean_rss_footer("") == ""
    assert clean_rss_footer(None) == ""


def test_clean_rss_footer_no_match():
    text = "Normal text with no footer patterns at all"
    assert clean_rss_footer(text) == text


def test_normalize_headline_multiple_prefixes():
    """Only the first matching prefix should be stripped."""
    from ingestion import normalize_headline
    assert normalize_headline("ФОТО: Галерија од настанот") == "Галерија од настанот"
    assert normalize_headline("ГАЛЕРИЈА: Слики од Скопје") == "Слики од Скопје"
    assert normalize_headline("ПОТВРДЕНО: Нов договор") == "Нов договор"
    assert normalize_headline("СКАНДАЛ: Откривање") == "Откривање"
    assert normalize_headline("УЖАС: Несреќа на пат") == "Несреќа на пат"
    assert normalize_headline("ТРАГЕДИЈА: Жртви") == "Жртви"


def test_normalize_headline_html_tags():
    from ingestion import normalize_headline
    assert normalize_headline("<p>Текст</p>") == "Текст"
    assert normalize_headline("<b>Важно</b> <i>резиме</i>") == "Важно резиме"
