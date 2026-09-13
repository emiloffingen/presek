"""Briefing cluster filters, grounding gates, and editorial quality checks."""

from __future__ import annotations

import re

from core.editorial_quality import (
    has_repetitive_media_framing,
    has_unprofessional_editorial_artifact,
    weak_editorial_abstraction_count,
)
from tasks.utils import log

_BRIEFING_PARTISAN_MARKERS = {
    "vo ocajna potraga",
    "krah sistem",
    "slavi pobeda",
    "predavstvo",
    "skandal",
    "sokantno",
    "udri",
    "zestoko",
    "katastrofa",
}

_BRIEFING_PARTY_PREFIXES = (
    "vmro-dpmne:",
    "sdsm:",
    "dui:",
    "vredi:",
    "levica:",
    "znam:",
    "allijansa za albancite:",
    "alternativa:",
    "grom:",
    "dpa:",
    "nsdp:",
)

_BRIEFING_LOW_SIGNAL_TITLE_MARKERS = (
    "vremenska prognoza",
    "najstudeno",
    "soncevo",
    "relativno toplo",
    "promocija na aktivnostite",
    "po povod 100 godini",
    "godini Beograd zoo",
    "svecenost",
    "odbelezuvanje",
    "godisnina",
    "horoskop",
    "хороскоп",
    "astro",
    "астро",
    "loto",
    "лото",
    "lotarija",
    "лотарија",
    "tv programa",
    "тв програма",
)


_BRIEFING_PUBLIC_INTEREST_MARKERS = (
    "izbor",
    "izbori",
    "izbirack",
    "glasanj",
    "parlamentarn",
    "sud",
    "pravosud",
    "zemjotres",
    "pozar",
    "vlada",
    "sobranie",
    "zakon",
    "odluka",
    "minister",
    "obvinitel",
    "polic",
    "liban",
    "on",
    "obedinetite nacii",
    "napad",
    "bezbed",
    "referendum",
)

_BRIEFING_WEATHER_MARKERS = (
    "vreme",
    "vremenska prognoza",
    "soncevo",
    "oblacnost",
    "temperatura",
    "najstudeno",
    "uhmr",
    "veter",
    "vrnezi",
)

_BRIEFING_SEVERE_WEATHER_MARKERS = (
    "nevreme",
    "portokalov",
    "crven alarm",
    "predupreduvanje",
    "poplava",
    "silen veter",
    "grad",
    "ekstremna temperatura",
    "zolt alarm",
)

_BRIEFING_SPORTS_MARKERS = (
    "nba",
    "nfl",
    "mlb",
    "nhl",
    "mvp",
    "нба",
    "kosarka",
    "košarka",
    "кошarka",
    "кошарка",
    "fudbal",
    "фудбал",
    "football",
    " gol",
    " golot",
    " gol ",
    " gol/",
    " гол",
    " голот",
    " гол ",
    "utakmica",
    "utakmici",
    "утакмица",
    "natprevar",
    "натпревар",
    "finale",
    "финалето",
    "финалната",
    "финална",
    "finalna serija",
    "finalnata serija",
    "playoff",
    "play-off",
    "premier league",
    "liga na sampioni",
    "liga na shampioni",
    "svetsko prvenstvo",
    "svetskoto prvenstvo",
    "mundial",
    "mundijal",
    "euro 202",
    "world cup",
    "sportmediа",
    "sport media",
    "sportklub",
    "transfer",
    "pobeda so",
    "poraz od",
    "rezultat",
    "rezultati",
    "pogodok",
    "asistencija",
    "titula",
    "sampion",
    "shampion",
    "шampion",
)

_BRIEFING_SPORTS_SOURCE_MARKERS = (
    "sportmedia",
    "sport media",
    "sportklub",
    "sportmediа",
    "спортmedia",
    "спортmediа",
    "ekipa.mk",
)

_BRIEFING_AMBIGUOUS_SPORTS_MARKERS = (
    "rezultat",
    "rezultati",
    "titula",
    "титула",
)

_BRIEFING_UNAMBIGUOUS_SPORTS_MARKERS = tuple(
    marker for marker in _BRIEFING_SPORTS_MARKERS if marker not in _BRIEFING_AMBIGUOUS_SPORTS_MARKERS
)

_BRIEFING_MAJOR_SPORTS_MARKERS = (
    "reprezentacija",
    "reprezentativ",
    "reprezentativci",
    "skandal",
    "istraga",
    "huligan",
    "nasil",
    "diskvalifik",
    "doping",
    "federacija",
    "obvinitel",
    "korupc",
    "korupci",
)


def _is_party_press_release_title(title: str) -> bool:
    clean = str(title or "").strip().casefold()
    return bool(clean) and clean.startswith(_BRIEFING_PARTY_PREFIXES)


_BRIEFING_PUBLIC_INTEREST_BOUNDARY_MARKERS = {
    "on",
    "vlada",
    "liban",
    "polic",
    "napad",
    "bezbed",
}


def _has_public_interest_signal(title: str, description: str = "", cluster_summary: str = "") -> bool:
    haystack = " ".join([str(title or ""), str(description or ""), str(cluster_summary or "")]).casefold()
    for marker in _BRIEFING_PUBLIC_INTEREST_MARKERS:
        if marker in _BRIEFING_PUBLIC_INTEREST_BOUNDARY_MARKERS or len(marker) < 4:
            if re.search(rf"(?<![a-z\u0400-\u04ff]){re.escape(marker)}(?![a-z\u0400-\u04ff])", haystack):
                return True
            continue
        if marker in haystack:
            return True
    return False


def _is_low_signal_briefing_cluster(title: str, description: str = "", cluster_summary: str = "") -> bool:
    haystack = " ".join([str(title or ""), str(description or ""), str(cluster_summary or "")]).casefold()
    return any(marker in haystack for marker in _BRIEFING_LOW_SIGNAL_TITLE_MARKERS)


def _is_routine_weather_cluster(title: str, description: str = "", cluster_summary: str = "") -> bool:
    haystack = " ".join([str(title or ""), str(description or ""), str(cluster_summary or "")]).casefold()
    if not any(marker in haystack for marker in _BRIEFING_WEATHER_MARKERS):
        return False
    return not any(marker in haystack for marker in _BRIEFING_SEVERE_WEATHER_MARKERS)


def _has_routine_sports_marker(haystack: str, category: str = "", topic: str = "") -> bool:
    unambiguous_hits = any(marker in haystack for marker in _BRIEFING_UNAMBIGUOUS_SPORTS_MARKERS)
    if unambiguous_hits:
        return True
    ambiguous_hits = any(marker in haystack for marker in _BRIEFING_AMBIGUOUS_SPORTS_MARKERS)
    if not ambiguous_hits:
        return False
    normalized_category = str(category or "").casefold()
    normalized_topic = str(topic or "").casefold()
    return normalized_category in {"sport", "sports", "sportovi"} or normalized_topic in {
        "sport",
        "sports",
        "sportovi",
    }


def _is_routine_sports_cluster(
    title: str,
    description: str = "",
    cluster_summary: str = "",
    category: str = "",
    topic: str = "",
    extra_context: str = "",
) -> bool:
    haystack = " ".join(
        [
            str(title or ""),
            str(description or ""),
            str(cluster_summary or ""),
            str(category or ""),
            str(topic or ""),
            str(extra_context or ""),
        ]
    ).casefold()
    if _has_public_interest_signal(title, description):
        return False
    if any(marker in haystack for marker in _BRIEFING_MAJOR_SPORTS_MARKERS):
        return False
    if str(category or "").casefold() in {"sport", "sports", "sportovi"}:
        return True
    if str(topic or "").casefold() in {"sport", "sports", "sportovi"}:
        return True
    if any(marker in haystack for marker in _BRIEFING_SPORTS_SOURCE_MARKERS):
        return True
    return _has_routine_sports_marker(haystack, category=category, topic=topic)


def _allow_partisan_briefing_cluster(
    title: str,
    source_count: int,
    has_editorial_depth: bool,
    has_synthesis: bool,
    has_public_interest: bool,
) -> bool:
    if not _is_party_press_release_title(title):
        return True
    if has_editorial_depth and has_public_interest:
        return True
    return source_count >= 10 and has_synthesis and has_public_interest


def _briefing_title_penalty(title: str, source_count: int = 1, has_editorial_depth: bool = False) -> float:
    clean = str(title or "").strip()
    lowered = clean.casefold()
    penalty = 0.0

    if re.match(r"^[A-Za-z0-9\-]{2,}:\s", clean):
        penalty += 1.8
    if any(marker in lowered for marker in _BRIEFING_PARTISAN_MARKERS):
        penalty += 1.8
    if clean.count("!") >= 1 or clean.count("?") >= 2:
        penalty += 0.35
    if source_count >= 6:
        penalty *= 0.8
    if has_editorial_depth:
        penalty *= 0.75
    return penalty


_GROUNDING_DEFINITE_SUFFIXES = (
    "iot",
    "iota",
    "ata",
    "eto",
    "nite",
    "neto",
    "nata",
    "ski",
    "ska",
    "sko",
    "cki",
    "cka",
    "cko",
)

_GROUNDING_TOKEN_RE = re.compile(r"[A-Za-z\u0400-\u04FF]{3,}", re.UNICODE)


def _normalize_grounding_token(word: str) -> str:
    from nlp.utils import transliterate

    token = transliterate(str(word or "").strip()).casefold()
    if not token:
        return ""
    for suffix in sorted(_GROUNDING_DEFINITE_SUFFIXES, key=len, reverse=True):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    token = token.replace("ij", "i").replace("iy", "i")
    return token


def _grounding_tokens_from_text(text: str) -> set[str]:
    from nlp.utils import transliterate

    source = transliterate(text).casefold()
    tokens: set[str] = set()
    for raw in _GROUNDING_TOKEN_RE.findall(source):
        norm = _normalize_grounding_token(raw)
        if len(norm) < 3:
            continue
        tokens.add(norm)
        if len(norm) >= 5:
            tokens.add(norm[:5])
    return tokens


def _grounding_word_in_context(word: str, source_latin: str, context_tokens: set[str]) -> bool:
    norm = _normalize_grounding_token(word)
    if len(norm) < 4:
        return True
    if norm in source_latin or norm in context_tokens:
        return True
    if len(norm) >= 5 and norm[:5] in context_tokens:
        return True
    for ctx in context_tokens:
        if len(ctx) >= 5 and len(norm) >= 5 and (ctx.startswith(norm[:5]) or norm.startswith(ctx[:5])):
            return True
    return False


def _is_grounded_daily_brief(brief: str, context: str) -> bool:
    """Stricter than cluster synthesis: named entities in the brief must appear in context."""
    if not brief or not context:
        return True

    from nlp.keywords import _extract_capitalized_phrases
    from nlp.utils import transliterate

    source_latin = transliterate(context).casefold()
    context_tokens = _grounding_tokens_from_text(context)
    context_entities = {
        transliterate(phrase).casefold()
        for phrase in _extract_capitalized_phrases(context)
        if len(str(phrase or "").strip()) >= 4
    }

    role_prefixes = {"od", "vo", "na", "so", "za", "niz", "u", "iz", "premierot", "ministarot", "pretsedatelot"}
    editorial_label_prefixes = {
        "reakcija",
        "analiza",
        "pregled",
        "fokus",
        "nastavak",
        "komentar",
        "insajt",
        "signal",
        "odgovor",
        "scenario",
        "rizik",
    }
    phrase_prefixes = role_prefixes | editorial_label_prefixes
    section_prefixes = {
        "velika slika",
        "ključne teme",
        "kljucne teme",
        "globalne i lokalne ose",
        "medijski radar",
        "sta pratiti",
        "dnevni brifing",
        "golemata slika",
        "globalni i lokalni oski",
        "mediumski radar",
        "sto da se sledi",
        "dneven briefing",
        "kljucni aspekt",
        "zasto je vazno",
    }

    for phrase in _extract_capitalized_phrases(brief):
        clean = str(phrase or "").strip().replace("\n", " ")
        if len(clean) < 4:
            continue

        words = [part for part in clean.replace("-", " ").split() if part]
        if words and words[0].casefold() in phrase_prefixes:
            words = words[1:]
            clean = " ".join(words)
            if len(clean) < 3:
                continue

        if len(words) < 2 and not clean.isupper():
            continue

        folded = transliterate(clean).casefold()
        if any(folded == prefix or folded.startswith(f"{prefix} ") for prefix in section_prefixes):
            continue
        if folded in context_entities or folded in source_latin:
            continue
        if _normalize_grounding_token(clean) in context_tokens:
            continue

        significant_words = [
            word for word in words if len(word) >= 4 and transliterate(word).casefold() not in phrase_prefixes
        ]
        if significant_words and all(
            _grounding_word_in_context(word, source_latin, context_tokens) for word in significant_words
        ):
            continue

        # Model-generated section labels (Reakcija, Optužbe, ...) may not appear verbatim
        # in source copy while the named entities that follow still do.
        if len(significant_words) >= 2:
            tail_words = significant_words[1:]
            if (
                tail_words
                and all(_grounding_word_in_context(word, source_latin, context_tokens) for word in tail_words)
                and not _grounding_word_in_context(significant_words[0], source_latin, context_tokens)
            ):
                continue

        log.warning(f"[briefing] Ungrounded entity in daily brief: {clean}")
        return False

    return True


def _has_valid_daily_brief_structure(brief: str, lang: str = "sr") -> bool:
    text = str(brief or "").strip()
    if not text:
        return False

    # Language-aware section markers
    if lang == "sr":
        required_phrases = [
            "Velika Slika",
            "Ključne teme",
            "Medijski Radar",
            "Šta pratiti",
        ]
    else:  # mk
        required_phrases = [
            "Големата Слика",
            "Клучни теми",
            "Медиумски Радар",
            "Што да се следи",
            # Fallback to Latin just in case
            "Golemata Slika",
            "Kljucni temi",
            "Mediumski Radar",
            "Sto da se sledi",
        ]

    found_count = 0
    lower_text = text.lower()
    for phrase in required_phrases:
        if phrase.lower() in lower_text:
            found_count += 1

    # For MK, we have more fallbacks, so found_count might be higher than 4
    # We just need at least 3 distinct semantic sections
    min_required = 3

    if found_count < min_required:
        log.warning(
            f"[briefing-debug] Required sections missing for {lang}. Found {found_count}/{min_required}+. Text: {text[:200]}..."
        )
        return False
    return True


def _is_high_quality_briefing(brief: str) -> bool:
    text = str(brief or "").strip()
    if not text:
        return False
    vague_markers = [
        "ce pokaze",
        "ostaje vazno",
        "moze da vlijae",
        "vredi da se sledi",
        "ostaje da se vidi",
        "doprva ce",
        "vremeto ce pokaze",
        "ќе покаже",
        "останува важно",
        "може да влијае",
        "вреди да се следи",
        "останува да се види",
        "допрва ќе",
        "времето ќе покаже",
        "клучно е да се напомене",
        "важно е да се истакне",
        "од витално значење",
        "sve u svemu",
        "ključno je napomenuti",
        "važno je istaći",
        "od vitalnog značaja",
        "globalne i lokalne ose napetosti",
        "preplitanje unutrašnjih i spoljašnjih napetosti",
        "legitimnost institucija",
        "širi trend",
        "šira neizvesnost",
        "simbol šire",
    ]
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        return False
    vague_count = sum(1 for line in lines if any(marker in line.lower() for marker in vague_markers))
    vague_pct = (vague_count / len(lines)) * 100
    if vague_pct > 25:
        log.warning(f"[editorial] Briefing rejected: too vague ({vague_pct:.1f}% filler)")
        return False
    weak_count = weak_editorial_abstraction_count(text)
    if weak_count > 0:
        log.warning(f"[editorial] Briefing rejected: unsupported abstraction ({weak_count} weak pattern hits)")
        return False
    if has_repetitive_media_framing(text):
        log.warning("[editorial] Briefing rejected: repetitive source-comparison phrasing")
        return False
    if has_unprofessional_editorial_artifact(text):
        log.warning("[editorial] Briefing rejected: unprofessional editorial artifact")
        return False
    sentence_starts = [line[:15].lower() for line in lines if len(line) > 15]
    unique_starts = len(set(sentence_starts))
    if len(sentence_starts) > 5 and unique_starts < 3:
        log.warning("[editorial] Briefing rejected: repetitive sentence structure")
        return False
    return True
