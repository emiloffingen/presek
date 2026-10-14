"""Named-entity extraction for Macedonian news headlines (no model, no spaCy).

Headlines are sentence-case, so "is this word capitalised?" is a weak signal on its own:
every sentence opener («Според», «Комедијата») looks like a name. The extractor combines
three cheap signals instead:

1. position: a capitalised word that only opens a sentence is not evidence of a name;
2. corpus statistics (`NameStats`): a word that is usually written lowercase elsewhere
   in the corpus («владата», «општина») is a common noun, one that is almost always
   capitalised mid-sentence («Мицкоски», «Скопје») is a name;
3. shape: adjacent capitalised words form one name («Мајкл Керик»), and a lone surname
   is folded into the one full name it belongs to («Трамп» -> «Доналд Трамп»).

Everything here is pure (no database), so it is cheap to test; `tasks.extractive_maintenance`
owns the I/O.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

log = logging.getLogger("presek.entities")

# Capitalised words that are never names: function words headlines open with, bylines and
# media tags, generic role nouns. Compared case-insensitively. NameStats catches most of
# these on its own; the list covers words too rare for the statistics to judge.
NOT_NAMES = frozenset(
    {
        "според", "тој", "таа", "тоа", "тие", "ова", "оваа", "овој", "овие", "она", "оној",
        "при", "кон", "над", "под", "пред", "меѓу", "преку", "околу", "после", "само", "уште",
        "дали", "зошто", "кога", "каде", "колку", "сите", "секој", "нема", "има", "ќе", "би",
        "видео", "фото", "текстот", "текст", "изворот", "извор", "анализа", "интервју", "ексклузивно",
        "општина", "општината", "република", "владата", "министерството", "министерот",
        "фон", "претседателот", "премиерот", "градоначалникот", "европската", "северна", "лигата",
        "и", "во", "на", "за", "од", "со", "не", "се", "го", "ја", "ги", "е", "што", "кој", "која",
        "кое", "како", "или", "ама", "но", "дека", "по", "the", "and", "for", "with", "from",
        "that", "this", "are", "was",
    }
)  # fmt: skip

# Tokens that mark an organisation when they appear inside a multi-word name.
_ORG_WORDS = frozenset(
    {
        "партија", "банка", "универзитет", "група", "group", "inc", "ltd", "фонд", "сојуз", "комисија",
        "агенција", "институт", "центар", "фондација", "здружение", "клуб", "фк", "рк", "кк",
        "корпорација", "компанија", "министерство", "собрание", "совет",
    }
)  # fmt: skip

# Countries and the cities that dominate Macedonian news. Not exhaustive: unknown places fall
# back to MISC, which is harmless. Casefolded.
_PLACES = frozenset(
    {
        "македонија", "северна македонија", "скопје", "битола", "охрид", "тетово", "куманово", "прилеп",
        "велес", "штип", "струмица", "кочани", "гевгелија", "струга", "гостивар", "кичево", "радовиш",
        "србија", "бугарија", "грција", "албанија", "косово", "хрватска", "словенија", "босна",
        "црна гора", "турција", "русија", "украина", "сад", "германија", "франција", "италија",
        "англија", "велика британија", "шпанија", "кина", "јапонија", "израел", "иран", "ирак",
        "сирија", "палестина", "газа", "австрија", "унгарија", "романија", "полска", "холандија",
        "белгија", "швајцарија", "канада", "индија", "америка", "европа", "азија", "африка", "балкан",
        "виена", "брисел", "москва", "киев", "вашингтон", "лондон", "париз", "берлин", "рим",
        "мадрид", "атина", "софија", "белград", "загреб", "тирана", "приштина", "анкара", "истанбул",
        "њујорк", "сараево", "подгорица", "љубљана", "букурешт", "будимпешта", "варшава",
    }
)  # fmt: skip

_WORD = re.compile(r"[^\W\d_][\w\-]*", re.UNICODE)
_OPENER_GAP = re.compile(r"[.!?:„“\"«()\n]\s*$")
# Macedonian definite-article endings: «Законот», «Комисијата», «Обвинителството». A lone
# capitalised word like this is a common noun unless the corpus says otherwise.
_DEFINITE_FORM = re.compile(r"(?:от|иот|ата|ото|ите)$")
# Institution nouns that are common words on their own but fine inside a longer name
# («Европска унија», «Врховен суд»). Many outlets title-case them, so NameStats cannot be
# trusted to reject them.
_GENERIC_ALONE = frozenset(
    {
        "министерство", "комисија", "совет", "собрание", "суд", "влада", "партија", "сојуз", "унија",
        "управа", "агенција", "фонд", "банка", "општина", "град", "закон", "одбор", "канцеларија",
        "подружница", "претседател", "премиер", "министер", "народ", "граѓани",
    }
)  # fmt: skip
# Slavic surname endings; only these lone words are folded into a full name (see build_aliases).
_SURNAME_ENDING = re.compile(r"(?:ов|ев|ова|ева|ски|ска|ин|ина|ќ|ић|ич|ак|ек|ко)$")
# «Михаилова» / «Михајлова»: outlets spell the same surname with и or ј before the consonant.
# Fold to the ј form so both spellings are one entity (same idea as core.trending's fold).
_SURNAME_I_FOR_J = re.compile(r"([ае])и([бцдфгхклмнпрстзв])(?=(?:ов|ев)(?:а|и|у|е|о|ом|ој|их|им|има)?$)")
MAX_NAME_TOKENS = 3
MAX_NAMES_PER_TEXT = 12
# Minimum corpus occurrences before NameStats is allowed to overrule the shape heuristics.
MIN_EVIDENCE = 3
NAME_RATIO = 0.6
COMMON_NOUN_RATIO = 0.4


@dataclass(frozen=True)
class Token:
    word: str
    start: int
    end: int
    opens_sentence: bool
    joins_previous: bool  # separated from the previous word by exactly one space
    before_pause: bool  # followed by ":" or ","


def _tokens(text: str) -> Iterator[Token]:
    prev_end = 0
    for m in _WORD.finditer(text):
        gap = text[prev_end : m.start()]
        yield Token(
            word=m.group(),
            start=m.start(),
            end=m.end(),
            opens_sentence=m.start() == 0 or bool(_OPENER_GAP.search(gap)),
            joins_previous=gap == " ",
            before_pause=text[m.end() : m.end() + 1] in (":", ","),
        )
        prev_end = m.end()


def _is_acronym(word: str) -> bool:
    return len(word) >= 2 and word.isupper()


def _is_capitalised(word: str) -> bool:
    return word[:1].isupper()


class NameStats:
    """How often each word is written capitalised mid-sentence vs lowercase in a corpus."""

    def __init__(self) -> None:
        self._capitalised: Counter[str] = Counter()
        self._lowercase: Counter[str] = Counter()

    def add_text(self, text: str) -> None:
        text = str(text or "")
        if not text or text == text.upper():
            return
        for tok in _tokens(text):
            if len(tok.word) < 3:
                continue
            key = tok.word.casefold()
            if tok.word.islower():
                self._lowercase[key] += 1
            elif _is_capitalised(tok.word) and not tok.opens_sentence:
                self._capitalised[key] += 1

    def add_texts(self, texts: Iterable[str]) -> NameStats:
        for text in texts:
            self.add_text(text)
        return self

    def name_ratio(self, word: str) -> float | None:
        """Share of the word's informative occurrences that are capitalised; None if unknown."""
        key = word.casefold()
        cap, low = self._capitalised[key], self._lowercase[key]
        if cap + low < MIN_EVIDENCE:
            return None
        return cap / (cap + low)

    def is_common_noun(self, word: str) -> bool:
        ratio = self.name_ratio(word)
        return ratio is not None and ratio < COMMON_NOUN_RATIO

    def is_known_name(self, word: str) -> bool:
        ratio = self.name_ratio(word)
        return ratio is not None and ratio >= NAME_RATIO


def _usable(tok: Token, stats: NameStats | None) -> bool:
    word = tok.word
    if not _is_capitalised(word):
        return False
    if not (len(word) >= 3 or _is_acronym(word)):
        return False
    if word.casefold() in NOT_NAMES:
        return False
    return not (stats is not None and not _is_acronym(word) and stats.is_common_noun(word))


def extract_names(text: str, stats: NameStats | None = None) -> list[str]:
    """Candidate names in `text`, in order of appearance, without duplicates."""
    text = str(text or "")
    if not text or text == text.upper():
        return []  # an all-caps headline carries no capitalisation signal
    names: list[str] = []
    run: list[Token] = []

    def flush() -> None:
        if not run:
            return
        first = run[0]
        if len(run) > 1 and all(_is_acronym(t.word) for t in run):
            run.clear()  # an all-caps phrase inside mixed text is shouting, not a name
            return
        if len(run) == 1 and not _is_acronym(first.word):
            folded = first.word.casefold()
            if folded in _GENERIC_ALONE or (_DEFINITE_FORM.search(folded) and len(folded) >= 6):
                run.clear()
                return
        if len(run) == 1 and first.opens_sentence:
            # A lone sentence opener is a name only if it is an acronym, introduces a quote
            # ("Воркапиќ: ..."), or the corpus shows it is usually capitalised mid-sentence.
            known = stats is not None and stats.is_known_name(first.word)
            if not (_is_acronym(first.word) or first.before_pause or known):
                run.clear()
                return
        name = " ".join(t.word for t in run)
        if name not in names:
            names.append(name)
        run.clear()

    for tok in _tokens(text):
        if _usable(tok, stats):
            if run and tok.joins_previous and len(run) < MAX_NAME_TOKENS:
                run.append(tok)
                continue
            flush()
            run.append(tok)
        else:
            flush()
    flush()
    return list(dict.fromkeys(tidy_name(n) for n in names))[:MAX_NAMES_PER_TEXT]


def tidy_name(name: str) -> str:
    """Canonical surface form: «СОФИЈА» -> «Софија», «Михаилова» -> «Михајлова»."""
    if name.isupper() and len(name) > 3 and name.casefold() in _PLACES:
        name = name.title()
    return " ".join(_SURNAME_I_FOR_J.sub(r"\1ј\2", part) for part in name.split())


def classify_entity(name: str) -> str:
    """PER / ORG / LOC / MISC from the shape of the name; there is no model behind this."""
    folded = name.casefold()
    parts = name.split()
    if folded in _PLACES:
        return "LOC"
    if len(parts) == 1:
        return "ORG" if _is_acronym(name) else "MISC"
    if any(p.casefold() in _ORG_WORDS or _is_acronym(p) for p in parts):
        return "ORG"
    if any(p.casefold() in _PLACES for p in parts):
        return "MISC"  # clubs and compound places («Атлетико Мадрид», «Црното Море»)
    return "PER"


def build_aliases(names: Iterable[str]) -> dict[str, str]:
    """Map lone surnames to the one full name they belong to ({"Трамп": "Доналд Трамп"}).

    A surname is folded only when it looks like a surname (Slavic ending, not a place) and
    exactly one multi-word name ends with it; with two candidates («Доналд Трамп»,
    «Мелани Трамп») it is ambiguous and stays alone. Without the ending test «Мајами» would
    fold into «Интер Мајами» and «Американци» into «Повеќето Американци», and a wrong
    merge is worse than a duplicate.
    """
    names = set(names)
    by_last: dict[str, set[str]] = defaultdict(set)
    for name in names:
        parts = name.split()
        # a definite-form word in the name («Германецот Александер Зверев») means the run
        # swallowed a common noun, so it is no safe alias target
        if any(_DEFINITE_FORM.search(p.casefold()) and len(p) >= 6 for p in parts):
            continue
        if len(parts) >= 2 and classify_entity(name) == "PER":
            by_last[parts[-1].casefold()].add(name)
    aliases: dict[str, str] = {}
    for name in names:
        if " " in name or _is_acronym(name) or name.casefold() in _PLACES:
            continue
        if not _SURNAME_ENDING.search(name.casefold()):
            continue
        full = by_last.get(name.casefold(), set())
        if len(full) == 1:
            aliases[name] = next(iter(full))
    return aliases


@dataclass
class ClusterEntity:
    name: str
    type: str
    mentions: int = 0  # articles that mention the name
    in_title: int = 0  # ... of which in the headline
    _seen: set[int] = field(default_factory=set, repr=False)


def extract_cluster_entities(
    articles: Iterable[dict],
    stats: NameStats | None = None,
    aliases: dict[str, str] | None = None,
    max_entities: int = 8,
) -> list[dict]:
    """Entities for one cluster, strongest first.

    A name is kept when it is in a headline or in at least two articles: a name that shows
    up once, in one description, is far more often noise than the story's subject.
    """
    aliases = aliases or {}
    found: dict[str, ClusterEntity] = {}
    for idx, art in enumerate(articles):
        title_names = {aliases.get(n, n) for n in extract_names(art.get("title") or "", stats)}
        body_names = {aliases.get(n, n) for n in extract_names(art.get("description") or "", stats)}
        for name in title_names | body_names:
            ent = found.setdefault(name, ClusterEntity(name=name, type=classify_entity(name)))
            if idx in ent._seen:
                continue
            ent._seen.add(idx)
            ent.mentions += 1
            if name in title_names:
                ent.in_title += 1
    kept = [e for e in found.values() if e.in_title or e.mentions >= 2]
    kept.sort(key=lambda e: (e.in_title, e.mentions, len(e.name)), reverse=True)
    return [{"name": e.name, "type": e.type, "mentions": e.mentions} for e in kept[:max_entities]]


# --- legacy API --------------------------------------------------------------
# Older call sites (synthesis sanitising, research, backfill) import these names.


def normalize_entity_name(name, *a, **kw):
    return re.sub(r"\s+", " ", str(name or "")).strip()


def extract_entities(text: str, max_entities: int = 5) -> list[dict]:
    """Entities of a single text, without corpus statistics."""
    return [{"name": n, "type": classify_entity(n)} for n in extract_names(text)[:max_entities]]


def validate_person_names(text):
    """Type-preserving pass-through (full name-hallucination fixer was removed)."""
    if text is None:
        return text
    if isinstance(text, list):
        return [str(t) for t in text]
    return str(text)


def update_knowledge_graph(entities, context_text: str = "") -> None:
    """No-op: `tasks.extractive.extract_entities_task` maintains knowledge_entities."""
    return
