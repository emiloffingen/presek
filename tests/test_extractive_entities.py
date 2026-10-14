import pytest

from tasks.extractive_maintenance import extract_entities_from_text


@pytest.mark.parametrize(
    "title, expected",
    [
        # sentence-opening function words are not entities
        ("Според министерството, цените растат", []),
        ("Ова е човекот кој загина во судирот", []),
        ("Тој ги одведе своите четири деца", []),
        # adjacent capitalised words become one name
        ("Мајкл Керик сакал да се откаже пред да го води Манчестер Јунајтед", ["Мајкл Керик", "Манчестер Јунајтед"]),
        # mid-sentence single names survive
        ("Бугарија треба да ја притвори бегалката од Македонија", ["Македонија"]),
        ("Лабораториските анализи покажаа дека водата во Скопје е безбедна", ["Скопје"]),
        # a lone opener survives only as an acronym or a quote introducer
        ("Воркапиќ: Ќе дадеме сè од себе", ["Воркапиќ"]),
        ("МВР соопшти дека сообраќајот е пуснат", ["МВР"]),
        # byline/media tags and role nouns are dropped
        ("Томовски е втор најдобар голман (ФОТО)", []),
        ("(ВИДЕО) Германец се обидел да влезе на Табановце", ["Табановце"]),
        ("Градоначалникот Пецаков оствари средба", ["Пецаков"]),
        # all-caps headlines have no capitalisation signal
        ("ГРЕЈНАТА СЕЗОНА ПОЧНА ПОРАНО", []),
        ("", []),
    ],
)
def test_extract_entities_from_text(title, expected):
    assert extract_entities_from_text(title) == expected
