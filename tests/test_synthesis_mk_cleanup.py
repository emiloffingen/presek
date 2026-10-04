from tasks.intelligence.synthesis_mk_cleanup import _clean_macedonian_spelling_and_script as clean


def test_bulgarian_forms_observed_in_production_are_repaired():
    assert clean("дипломатски обвинения") == "дипломатски обвинувања"
    assert clean("Русија продължува нападите") == "Русија продолжува нападите"
    assert clean("Комбинацията од високи цени") == "Комбинацијата од високи цени"
    assert clean("неблагоприятни временски услови") == "неповолни временски услови"


def test_serbian_and_bulgarian_words_are_repaired():
    assert clean("проблеми при буђење") == "проблеми при будење"
    assert clean("също и който") == "исто така и кој"


def test_letters_outside_the_macedonian_alphabet_never_survive():
    out = clean("я ю ы э ё й ђ ћ ъ")
    assert not any(ch in out for ch in "яюыэёйђћъ")
