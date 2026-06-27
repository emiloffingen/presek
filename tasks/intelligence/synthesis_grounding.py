"""Fact grounding and hallucination gates for synthesis quality."""

from __future__ import annotations

import re

from tasks.utils import log

def _synthesis_source_corpus(article_rows):
    return " ".join(
        part
        for article in article_rows or []
        for part in (
            str(article.get("title") or ""),
            str(article.get("description") or ""),
            str(article.get("full_content") or ""),
            str(article.get("summary") or ""),
        )
        if part
    )


def _normalize_number_token(token: str) -> str:
    import re

    clean = str(token or "").strip().rstrip("%")
    if not clean:
        return ""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", clean):
        return clean.replace(".", "")
    if "," in clean and "." not in clean:
        left, _, right = clean.partition(",")
        if right.isdigit() and len(right) <= 2:
            return f"{left}.{right}"
    return clean.replace(",", ".")


def _is_soft_number_token(token: str) -> bool:
    import re

    clean = str(token or "").strip().rstrip("%")
    if re.fullmatch(r"20[12]\d", clean):
        return True
    if re.fullmatch(r"19\d{2}", clean):
        return True
    return False


def _number_token_grounded_in_source(token, source_numbers, source_text_folded):
    clean = str(token or "").strip()
    if not clean:
        return True
    if _is_soft_number_token(clean):
        normalized_year = _normalize_number_token(clean)
        if any(_normalize_number_token(src) == normalized_year for src in source_numbers):
            return True
        if clean.casefold() in source_text_folded:
            return True
    if clean in source_numbers:
        return True
    if clean.casefold() in source_text_folded:
        return True
    normalized = _normalize_number_token(clean)
    if not normalized:
        return True
    if normalized.casefold() in source_text_folded:
        return True
    for src in source_numbers:
        if _normalize_number_token(src) == normalized:
            return True
    normalized_legacy = clean.replace(",", ".")
    for src in source_numbers:
        src_norm = str(src).replace(",", ".")
        if normalized_legacy == src_norm:
            return True
    return False


def _fact_grounding_diagnostics(
    synthesis_text: str,
    article_rows,
    lang: str = "sr",
    *,
    fast_mode: bool = False,
) -> dict:
    """Return fact-grounding diagnostics for synthesis quality gates."""
    if not synthesis_text or not article_rows:
        return {"ok": True, "ungrounded_numbers": [], "ungrounded_scores": []}

    from core.runtime_limits import FACT_GROUNDING_MAX_UNGROUNDED, FACT_GROUNDING_MAX_UNGROUNDED_FAST
    from nlp.generation import _extract_number_tokens, _extract_sports_scores
    from nlp.utils import transliterate

    source_text = transliterate(_synthesis_source_corpus(article_rows))
    source_folded = source_text.casefold()
    source_numbers = set(_extract_number_tokens(source_text))
    source_scores = set(_extract_sports_scores(source_text))

    synth_text = transliterate(str(synthesis_text or ""))
    synth_numbers = _extract_number_tokens(synth_text)
    synth_scores = _extract_sports_scores(synth_text)

    ungrounded_numbers = [
        token
        for token in synth_numbers
        if not _is_soft_number_token(token)
        and not _number_token_grounded_in_source(token, source_numbers, source_folded)
    ]
    max_ungrounded = FACT_GROUNDING_MAX_UNGROUNDED_FAST if fast_mode else FACT_GROUNDING_MAX_UNGROUNDED

    ungrounded_scores: list[str] = []
    if synth_scores:
        ungrounded_scores = [
            score
            for score in synth_scores
            if score not in source_scores and score.casefold() not in source_folded
        ]

    numbers_ok = len(ungrounded_numbers) <= max_ungrounded
    max_ungrounded_scores = 1 if fast_mode else 0
    scores_ok = len(ungrounded_scores) <= max_ungrounded_scores
    return {
        "ok": numbers_ok and scores_ok,
        "ungrounded_numbers": ungrounded_numbers[:8],
        "ungrounded_scores": ungrounded_scores[:4],
        "max_ungrounded_numbers": max_ungrounded,
        "lang": lang,
    }


def _is_fact_grounded_synthesis(synthesis_text: str, article_rows, lang: str = "sr", *, fast_mode: bool = False) -> bool:
    diagnostics = _fact_grounding_diagnostics(
        synthesis_text,
        article_rows,
        lang,
        fast_mode=fast_mode,
    )
    if not diagnostics["ok"]:
        if diagnostics["ungrounded_numbers"]:
            log.warning(
                "[ai/fact_gate] Ungrounded numbers in synthesis: %s",
                ", ".join(diagnostics["ungrounded_numbers"][:4]),
            )
        if diagnostics["ungrounded_scores"]:
            log.warning(
                "[ai/fact_gate] Ungrounded sports scores in synthesis: %s",
                ", ".join(diagnostics["ungrounded_scores"]),
            )
    return diagnostics["ok"]
def _is_grounded_synthesis(synthesis_text: str, source_context: str) -> bool:
    if not synthesis_text or not source_context:
        return True

    from nlp.keywords import _extract_capitalized_phrases
    from nlp.utils import transliterate

    source_latin = transliterate(source_context).casefold()
    context_entities = {
        transliterate(phrase).casefold()
        for phrase in _extract_capitalized_phrases(source_context)
        if len(str(phrase or "").strip()) >= 4
    }

    role_words = {
        "president",
        "prime",
        "minister",
        "premier",
        "serbian",
        "macedonian",
        "american",
        "russian",
        "ukrainian",
        "european",
        "pretsedatel",
        "pretsedatelot",
        "pretsedatelkata",
        "premierot",
        "premierkata",
        "premijer",
        "premijerka",
        "ministar",
        "ministarka",
        "ministerot",
        "ministerkata",
        "srpski",
        "srpska",
        "srpskog",
        "makedonski",
        "makedonska",
        "americki",
        "americka",
        "ruski",
        "ruska",
        "ukrajinski",
        "ukrajinska",
        "evropski",
        "evropska",
    }

    def _entity_words(value: str) -> list[str]:
        folded_value = transliterate(value or "").casefold()
        return [
            word
            for word in re.findall(r"[A-Za-z\u0400-\u04FF0-9-]{3,}", folded_value)
            if word not in role_words
        ]

    def _entity_is_grounded(value: str) -> bool:
        folded_value = transliterate(value or "").casefold().strip()
        if not folded_value:
            return True
        if folded_value in context_entities or folded_value in source_latin:
            return True

        words = _entity_words(value)
        if not words:
            return True

        # Role + partial name should pass when the actual name appears nearby in source.
        matched = 0
        for word in words:
            stem = word[:6] if len(word) > 7 else word
            if stem in source_latin or any(stem in entity for entity in context_entities):
                matched += 1

        if matched >= len(words):
            return True
        if len(words) >= 2 and matched >= len(words) - 1 and any(len(word) >= 6 for word in words):
            return True

        return False

    allowed_singletons = {
        "srbij",
        "beograd",
        "albanij",
        "eu",
        "vmro-dpmne",
        "iran",
        "ormuskiot tesnec",
        "dojran",
        "sad",
        "teksas",
        "nato",
        "obedinetite nacii",
        "on",
        "ukrain",
        "rusij",
        "sdsm",
        "vasington",
        "teheran",
        "bliskiot istok",
        "persiskiot zaliv",
        "zapadniot balkan",
        "evropskata unija",
        "brisel",
        "moskva",
        "kiev",
        "izrael",
        "gaza",
        "liban",
        "crna gora",
        "grcij",
        "bugarij",
        "makedon",
        "republik",
        "severn",
        "ahmet",
        "mickosk",
        "siljanovsk",
        "pendarovsk",
        "kovacevsk",
        "filipc",
        "gruevsk",
        "zaev",
        "presek",
        "bitol",
        "ohrid",
        "tetovo",
        "kumanovo",
        "gostivar",
        "skopj",
        "beograd",
        "vinic",
        "veles",
        "stip",
        "strumic",
        "prilep",
        "sri lanka",
        "kiribati",
        "si dzinping",
        "bajden",
        "tramp",
        "putin",
        "zelenski",
        "makron",
        "erdogan",
        "vucic",
        "rama",
        "osman",
        "maricic",
        "kostadinovska-stojcevska",
        "biserka",
        "bocvarski",
        "liga na sampioni",
        "premier liga",
        "real madrid",
        "barselona",
        "mancester junajted",
        "baern minhen",
        "stef kari",
        "lebron dzejms",
        "jokic",
        "doncic",
        "djokovic",
        "alkaraz",
        "siner",
        "janik siner",
        "vinisius",
        "vinisius zunior",
        "mbape",
        "haland",
        "elmas",
        "elif elmas",
        "pandev",
    }

    hard_hallucinations = 0
    soft_hallucinations = 0
    for phrase in _extract_capitalized_phrases(synthesis_text):
        clean = str(phrase or "").strip().replace("\n", " ")
        if len(clean) < 4:
            continue
        if clean.split()[0].lower() in {"od", "vo", "na", "so", "za", "niz", "u", "iz"}:
            clean_parts = clean.split()[1:]
            if not clean_parts:
                continue
            clean = " ".join(clean_parts)
            if len(clean) < 3:
                continue

        words = [part for part in clean.replace("-", " ").split() if part]
        is_acronym = clean.isupper()

        # Stricter check for multi-word entities (proper names)
        # Single words are often common nouns or noise, so we are more lenient
        if len(words) < 2 and not is_acronym:
            continue

        folded = transliterate(clean).casefold()
        if folded in context_entities:
            continue

        # Check allowed_singletons with word boundary awareness or as substrings for longer phrases
        is_allowed = False
        for allowed in allowed_singletons:
            if allowed == folded:
                is_allowed = True
                break
            if len(allowed) > 5 and allowed in folded:
                is_allowed = True
                break

        if is_allowed:
            continue

        if _entity_is_grounded(clean):
            continue

        core_words = _entity_words(clean)
        if is_acronym or len(core_words) >= 2:
            log.warning(f"[ai/hallucination] Hallucinated entity detected in synthesis: {clean} (folded: {folded})")
            hard_hallucinations += 1
        else:
            log.debug(f"[ai/hallucination] Suspicious but soft entity in synthesis: {clean} (folded: {folded})")
            soft_hallucinations += 1

    # Keep hard failures for truly ungrounded names, but allow a little noise from
    # translated titles and capitalization quirks in Serbian/Macedonian synthesis.
    if hard_hallucinations > 2:
        return False
    if hard_hallucinations >= 1 and len(synthesis_text) < 700:
        return False
    if hard_hallucinations >= 2 and len(synthesis_text) < 1400:
        return False
    if hard_hallucinations >= 1 and soft_hallucinations >= 4 and len(synthesis_text) < 1200:
        return False

    return True
