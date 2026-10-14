import pytest

from core.entities import (
    NameStats,
    build_aliases,
    classify_entity,
    extract_cluster_entities,
    extract_names,
)


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
def test_extract_names(title, expected):
    assert extract_names(title) == expected


def _stats() -> NameStats:
    corpus = [
        "Мицкоски најави нови мерки",
        "Премиерот Мицкоски се сретна со Трамп",
        "Реформите на Мицкоски се критикувани",
        "Опозицијата го критикува Мицкоски за буџетот",
        "Бугарија одговори на Мицкоски",
        "Експерти предупредуваат дека владата не е подготвена",
        "Опозицијата бара оставка, а владата молчи",
        "Не, владата донесе одлука",
        "Комедијата која ги полни салите",
        "Добра комедија и уште една комедија во Битола",
        "Нова комедија доаѓа во Скопје",
    ]
    return NameStats().add_texts(corpus)


def test_stats_reject_common_nouns_and_accept_known_names():
    stats = _stats()
    assert stats.is_common_noun("Владата")
    assert stats.is_common_noun("Комедијата") is False  # too little evidence either way
    assert stats.is_known_name("Мицкоски")


def test_stats_keep_a_known_name_that_opens_a_headline():
    # "Мицкоски" opens this headline with no colon: the shape heuristic would drop it
    assert extract_names("Мицкоски најави нови мерки") == []
    assert extract_names("Мицкоски најави нови мерки", _stats()) == ["Мицкоски"]


def test_stats_drop_a_common_noun_even_mid_sentence():
    assert extract_names("Протест пред Владата во Скопје", _stats()) == ["Скопје"]


def test_stats_never_drop_acronyms():
    assert extract_names("Одлука на МВР за границата", _stats()) == ["МВР"]


def test_build_aliases_folds_a_surname_into_its_one_full_name():
    assert build_aliases(["Зеленски", "Володимир Зеленски", "Скопје"]) == {"Зеленски": "Володимир Зеленски"}


def test_build_aliases_skips_full_names_that_swallowed_a_common_noun():
    assert build_aliases(["Зверев", "Германецот Александер Зверев"]) == {}


def test_build_aliases_does_not_fold_clubs_or_plurals():
    assert build_aliases(["Мајами", "Интер Мајами", "Американци", "Повеќето Американци"]) == {}


def test_build_aliases_leaves_an_ambiguous_surname_alone():
    assert build_aliases(["Петров", "Иван Петров", "Марко Петров"]) == {}


def test_build_aliases_ignores_org_names_and_acronyms():
    assert build_aliases(["СДСМ", "Универзитет Св. Кирил", "Кирил"]) == {}


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Мајкл Керик", "PER"),
        ("МВР", "ORG"),
        ("Фондација Сорос", "ORG"),
        ("Скопје", "LOC"),
        ("Македонија", "LOC"),
        ("Ван", "MISC"),
        ("Атлетико Мадрид", "MISC"),
    ],
)
def test_classify_entity(name, expected):
    assert classify_entity(name) == expected


def test_cluster_entities_need_a_headline_or_two_articles():
    arts = [
        {"title": "Мајкл Керик го презеде Манчестер Јунајтед", "description": "Станува збор за Охрид и Илинден."},
        {"title": "Нов тренер на клупата", "description": "Мајкл Керик потпиша договор. Се споменува Охрид."},
    ]
    got = {e["name"]: e["mentions"] for e in extract_cluster_entities(arts)}
    assert got["Мајкл Керик"] == 2
    assert got["Манчестер Јунајтед"] == 1  # headline mention is enough
    assert got["Охрид"] == 2  # two bodies, no headline
    assert "Илинден" not in got  # one description mention only


def test_cluster_entities_apply_aliases_and_rank_headline_names_first():
    arts = [
        {"title": "Средба на Трамп и Путин", "description": ""},
        {"title": "Средбата ја најави Доналд Трамп", "description": ""},
    ]
    aliases = {"Трамп": "Доналд Трамп"}  # build_aliases itself is stricter, see above
    got = extract_cluster_entities(arts, aliases=aliases)
    assert got[0]["name"] == "Доналд Трамп"
    assert got[0]["mentions"] == 2
    assert [e["type"] for e in got if e["name"] == "Доналд Трамп"] == ["PER"]


def test_cluster_entities_respect_max_entities():
    arts = [{"title": "Битола, Прилеп, Велес, Штип, Охрид, Тетово", "description": ""}]
    assert len(extract_cluster_entities(arts, max_entities=3)) == 3


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Руската војска нападна РУСИЈА НАПАЃА во Одеса", ["Одеса"]),
        ("Одлуката на Советот ја критикуваа од Брисел", ["Брисел"]),
        ("Во Белата Куќа се сретнаа лидерите", ["Белата Куќа"]),
        ("Во Министерство нема одговор од Скопје", ["Скопје"]),
        ("Европска унија го усвои пакетот", []),
        ("Одлука на Европска Унија за Украина", ["Европска Унија", "Украина"]),
    ],
)
def test_shouting_and_definite_nouns_are_not_names(text, expected):
    assert extract_names(text) == expected


def test_spelling_variants_of_a_surname_are_one_entity():
    assert extract_names("Одговорот на Ива Михаилова и на Ива Михајлова") == ["Ива Михајлова"]


def test_all_caps_places_are_title_cased_but_acronyms_are_not():
    assert extract_names("Одлука во СОФИЈА на САД и НАТО") == ["Софија", "САД", "НАТО"]
