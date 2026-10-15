"""Quote of the day: attribution, rejection of fragments, corroboration."""

from core.quotes import extract_quote, find_speaker, pick_quote_of_the_day

Q = "Ова е апсолутно неприфатливо – уште еден напад во непосредна близина на бугарските територијални води"


def _row(source, quote=Q, after=", рече Радев.", before="Претседателот го осуди нападот. ", cluster="c1", n=28):
    return {
        "cluster_id": cluster,
        "source": source,
        "n_sources": n,
        "title": "Дрон потона брод",
        "before_text": before,
        "quote_text": quote,
        "after_text": after,
    }


def test_speaker_after_quote():
    assert find_speaker("", ", рече Мицкоски. Промените треба") == "Мицкоски"
    assert find_speaker("", ", им рече Трамп на новинарите во Белата куќа") == "Трамп"


def test_speaker_with_role_and_full_name():
    assert find_speaker("", ", изјави премиерот Христијан Мицкоски на средба") == "Христијан Мицкоски"


def test_speaker_skips_agency_prefix():
    assert find_speaker("", ", изјави за АФП Дејвид Спигел, онколог кој истражува") == "Дејвид Спигел"


def test_speaker_before_quote():
    assert find_speaker("Минатата недела Рубио рече: ", " Нашата амбасадорка") == "Рубио"


def test_pronoun_is_not_a_speaker():
    assert find_speaker("", ", рече тој. Според Светската здравствена организација") is None


def test_reported_speech_is_not_a_speaker():
    assert find_speaker("", ", изјави дека Македонија е подготвена") is None


def test_fragment_rejected():
    assert extract_quote("", "ќе биде излечен и ракот никогаш нема да му го загрози животот", ", додаде Шпигел") is None


def test_nested_quote_marks_rejected():
    q = "Јазолот отстранет од папата за време на операцијата во болницата „Џемели"
    assert extract_quote("", q, ", соопшти Ватикан") is None


def test_short_span_rejected():
    assert extract_quote("", "Американско здружение за белодробни заболувања", ", изјави Мора") is None


def test_latin_text_rejected():
    q = "This is an English sentence that is long enough to pass the length rule easily"
    assert extract_quote("", q, ", рече Радев") is None


def test_unattributed_quote_rejected():
    assert extract_quote("", Q, ". Дополнителни детали не се познати.") is None


def test_picks_quote_carried_by_two_outlets_in_one_story():
    rows = [
        _row("Alfa"),
        _row("Kanal 5"),
        _row("Telma", quote="Тоа е нешто сосема друго што рече некој во една статија", after=", рече Петров."),
    ]
    picked = pick_quote_of_the_day(rows)
    assert picked["quote"] == Q
    assert picked["speaker"] == "Радев"
    assert picked["sources"] == 2
    assert picked["cluster_id"] == "c1"


def test_single_outlet_quote_is_not_shown():
    assert pick_quote_of_the_day([_row("Kanal 5")]) is None


def test_same_quote_in_different_stories_is_not_corroboration():
    assert pick_quote_of_the_day([_row("Alfa", cluster="a"), _row("Kanal 5", cluster="b")]) is None


def test_prefers_fuller_speaker_name():
    rows = [_row("Alfa", after=", рече Мицкоски."), _row("Telma", after=", рече Христијан Мицкоски.")]
    assert pick_quote_of_the_day(rows)["speaker"] == "Христијан Мицкоски"


def test_widely_covered_story_wins():
    other = "Проценуваме дека со текот на времето ќе бидат засегнати околу четириесет отсто од работните места"
    rows = [
        _row("Alfa", n=5, cluster="small", quote=other, after=", рече Георгиева."),
        _row("Telma", n=5, cluster="small", quote=other, after=", рече Георгиева."),
        _row("Alfa", n=28),
        _row("Telma", n=28),
    ]
    assert pick_quote_of_the_day(rows)["cluster_id"] == "c1"


def test_empty_input():
    assert pick_quote_of_the_day([]) is None


def test_quote_addressed_to_someone_is_rejected():
    q = "Должите уште судски трошоци од тужбата. На Апелација сега фатете некоја врска, инаку трошоци должите заради тоа што изгубивте спор"
    assert extract_quote("", q, ", рече Апасиев.") is None
    assert (
        extract_quote(
            "", "Вие сте одговорни за ова што се случува и мора да одговорите пред граѓаните", ", рече Рубио."
        )
        is None
    )


def test_statements_in_first_or_third_person_still_pass():
    assert extract_quote("", Q, ", рече Радев.") is not None
    q2 = "Министерството за внатрешни работи ги спроведе сите потребни мерки и најави дека истрагата ќе продолжи во следните денови"
    assert extract_quote("", q2, ", изјави Тошковски.")["speaker"] == "Тошковски"
