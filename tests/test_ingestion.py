import pytest
from ingestion import normalize_headline, clean_rss_footer

def test_normalize_headline():
    assert normalize_headline("ОВА Е НАСЛОВ СО ГОЛЕМИ БУКВИ") == "Ова Е Наслов Со Големи Букви"
    assert normalize_headline("Нормален наслов") == "Нормален наслов"
    assert normalize_headline("ВЛАДА: Нови мерки") == "ВЛАДА: Нови мерки" # Only partial upper
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