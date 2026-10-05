from tasks.intelligence.synthesis_mk_cleanup import _clean_macedonian_spelling_and_script as clean


def test_bulgarian_forms_observed_in_production_are_repaired():
    assert clean("дипломатски обвинения") == "дипломатски обвинувања"
    assert clean("Русија продължува нападите") == "Русија продолжува нападите"
    assert clean("Комбинацията од високи цени") == "Комбинацијата од високи цени"
    assert clean("неблагоприятни временски услови") == "неповолни временски услови"


def test_serbian_and_bulgarian_words_are_repaired():
    assert clean("проблеми при буђење") == "проблеми при будење"
    assert clean("също и който") == "исто така и кој"
    # Ambiguous ъ/ю are handled word-by-word (a blind letter map corrupts these)
    assert clean("продължи изключително") == "продолжи исклучително"
    assert clean("создале беспорядок") == "создале неред"


def test_letters_outside_the_macedonian_alphabet_never_survive():
    out = clean("я ы э ё й ђ ћ")
    assert not any(ch in out for ch in "яыэёйђћ")


def test_october_production_leaks_are_repaired():
    assert clean("тя сподели") == "таа сподели"
    assert clean("односите со Бугария") == "односите со Бугарија"
    assert clean("Исходът од битките") == "Исходот од битките"
    assert clean("главна атракция") == "главна атракција"
    assert clean("на Сајму за автомобили") == "на Саемот за автомобили"
    assert clean("несвакодневна пречка") == "несекојдневна пречка"
    assert clean("Любовта е клучна") == "Љубовта е клучна"
    assert clean("префрляйки ја топката") == "префрлајќи ја топката"
    assert clean("Тој подчерта важноста") == "Тој подвлече важноста"
    # Generic letter fallback still repairs Ukrainian spellings
    assert clean("изолація") == "изолација"
    assert clean("Дарія Шипилова") == "Дарија Шипилова"
    assert clean("своя прва") == "своја прва"


def test_october_round_two_production_leaks_are_repaired():
    assert clean("Становите се скъпаа") == "Становите се скапаа"
    assert clean("грешките ги скъсија победата") == "грешките ги скратија победата"
    assert clean("нова вълна на тензија") == "нова бран на тензија"
    assert clean("„ОхридНюз“ пренесува") == "„ОхридЊуз“ пренесува"
