import pytest

from core.text_extraction import strip_dangling_entity


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("потврди дека имало &bd...", "потврди дека имало..."),
        ("напиша: &bdq...", "напиша:..."),
        ("проект &ndas...", "проект..."),
        ("карактер &nda…", "карактер…"),
        ("cut here &#82", "cut here"),
        ("complete „quote&bdquo;...", "complete „quote&bdquo;..."),
        ("AT&T...", "AT&T..."),
        ("plain text", "plain text"),
        ("", ""),
    ],
)
def test_strip_dangling_entity(raw, expected):
    assert strip_dangling_entity(raw) == expected
