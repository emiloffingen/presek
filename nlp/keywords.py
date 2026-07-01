import os
import re
import threading
from collections import Counter

from core.trending import STOPWORDS
from nlp.utils import log

_keybert_model = None
_keybert_lock = threading.Lock()
_keybert_unavailable = False


def _get_keybert():
    """Lazy-load KeyBERT once, reusing the shared sentence-transformers model."""
    global _keybert_model, _keybert_unavailable
    if os.environ.get("PRESEK_DISABLE_KEYBERT", "").lower() in {"1", "true", "yes"}:
        return None
    if _keybert_unavailable:
        return None
    if _keybert_model is not None:
        return _keybert_model
    with _keybert_lock:
        if _keybert_model is not None:
            return _keybert_model
        try:
            from keybert import KeyBERT

            from core.embeddings import get_shared_model

            st_model = get_shared_model()
            if st_model is None:
                _keybert_unavailable = True
                return None
            _keybert_model = KeyBERT(model=st_model)
            log.info("[nlp.keywords] KeyBERT ready (sharing MiniLM embedding model)")
        except Exception as e:
            log.warning(f"[nlp.keywords] KeyBERT unavailable, using legacy keyphrases: {e}")
            _keybert_unavailable = True
            return None
        return _keybert_model


from core.localization import (
    ENTITY_NOISE_WORDS,
    PROTECTED_NAMES,
    SOURCE_NOISE_WORDS,
    TAG_GENERIC_STARTERS,
    TAG_MAPPINGS,
    TAG_NOISE_WORDS,
)

# Latin diacritics + Cyrillic used across MK/SR newswire text.
_SR_LATIN_LETTERS = "A-Za-z\u0106\u0107\u010C\u010D\u0110\u0111\u017D\u017E\u0160\u0161"
_CYRILLIC_LETTERS = r"\u0400-\u04FF"
WORD_CHAR_CLASS = rf"{_SR_LATIN_LETTERS}{_CYRILLIC_LETTERS}"
WORD_TOKEN_RE = re.compile(rf"[{WORD_CHAR_CLASS}]{{3,}}", re.UNICODE)
LAT_UPPER_CLASS = r"A-Z\u0400-\u042F\u0106\u010C\u0110\u017D\u0160"
LAT_LOWER_CLASS = r"a-z0-9\u0430-\u044F\u0450-\u045F\u0107\u010d\u0111\u017e\u0161"
_DIACRITIC_JOINERS = ("č", "ć", "š", "ž", "đ")
_DIACRITIC_SPLIT_SUFFIXES = frozenset(
    {
        "enih",
        "anih",
        "nih",
        "ama",
        "ima",
        "om",
        "oj",
        "og",
        "eg",
        "em",
        "ju",
        "ja",
        "je",
        "ji",
        "ca",
        "ce",
        "cu",
        "ka",
        "ke",
        "ki",
        "ku",
        "na",
        "ne",
        "ni",
        "nu",
        "ta",
        "te",
        "ti",
        "tu",
        "ga",
        "ge",
        "gi",
        "gu",
        "la",
        "le",
        "li",
        "lu",
        "ma",
        "me",
        "mi",
        "mu",
        "ra",
        "re",
        "ri",
        "ru",
        "va",
        "ve",
        "vi",
        "vu",
    }
)


def _repair_diacritic_fragment_tag(name: str) -> str:
    clean = re.sub(r"\s+", " ", str(name or "").strip())
    parts = clean.split(" ")
    if len(parts) != 2:
        return clean

    left, right = parts
    if any(ch in "čćšžđČĆŠŽĐ" for ch in clean):
        return clean
    if len(left) < 4 or len(right) < 3 or len(right) > 5:
        return clean
    if right.casefold() not in _DIACRITIC_SPLIT_SUFFIXES:
        return clean

    for joiner in _DIACRITIC_JOINERS:
        merged = f"{left}{joiner}{right}"
        if " " not in merged and len(merged) >= 6:
            return merged
    return clean


def normalize_tag_name(name):
    clean = _repair_diacritic_fragment_tag(name)
    clean = re.sub(r"\s+", " ", str(clean or "").strip(" -–—,.;:!?()[]{}\"'"))
    if not clean:
        return ""

    # Handle single character or numeric noise
    if len(clean) < 3 or clean.isdigit():
        return ""

    lowered = clean.lower()

    # 1. Handle dynamic mappings
    if lowered in TAG_MAPPINGS:
        return TAG_MAPPINGS[lowered]

    # 2. Handle dynamic protected names
    if lowered in PROTECTED_NAMES:
        if lowered == "makedon":
            return "Makedon"
        if "makedon" in lowered:
            return "Makedonija"
        if "amerika" in lowered:
            return "Amerika"
        return clean.capitalize()

    # 2. Basic Macedonian Definite Article Stripping (Conservative)
    # Only strip if the word remains long enough, it is a single word, and it's a common suffix
    if " " not in clean and len(clean) > 7:  # Higher threshold to protect words like 'Kuca'
        if clean.endswith("to") or clean.endswith("ta"):
            clean = clean[:-2]
        elif clean.endswith("ot"):
            clean = clean[:-2]
        elif clean.endswith("te"):
            clean = clean[:-2]

    # 3. Selective suffix stripping (adjectives -> nouns where clear)
    if len(clean) > 8:
        if not clean.lower().endswith("nija"):
            if not any(
                lowered.startswith(p)
                for p in [
                    "makedon",
                    "mickos",
                    "amerik",
                    "evrop",
                    "rusij",
                    "izrael",
                    "ukrain",
                ]
            ):
                clean = re.sub(
                    r"(ovski|evski|skiot|skata|skoto|skite)$",
                    "",
                    clean,
                    flags=re.IGNORECASE,
                )
                if clean.lower().endswith("ski") and len(clean) > 5:
                    clean = re.sub(r"ski$", "", clean, flags=re.IGNORECASE)

    # 4. Capitalization fallback
    if re.fullmatch(rf"[{WORD_CHAR_CLASS}\s-]+", clean) and clean.islower():
        if " " in clean:
            parts = clean.split(" ")
            clean = parts[0].capitalize() + " " + " ".join(parts[1:])
        else:
            clean = clean.capitalize()

    # 5. Final pass against noise
    if clean.lower() in TAG_NOISE_WORDS or len(clean) < 3:
        return ""

    return clean.strip()


# Locative/genitive surface forms scraped from headlines → canonical entity labels.
FOCUS_ENTITY_SURFACE_NORMALIZATIONS = {
    "srbije": "Srbija",
    "srbiji": "Srbija",
    "srbijom": "Srbija",
    "srbiju": "Srbija",
    "србије": "Србија",
    "србији": "Србија",
    "србијом": "Србија",
    "србију": "Србија",
    "beogradu": "Beograd",
    "beograda": "Beograd",
    "београду": "Београд",
    "београда": "Београд",
    "evrope": "Evropa",
    "evropi": "Evropa",
    "evropu": "Evropa",
    "европе": "Европа",
    "европи": "Европа",
    "европу": "Европа",
    "kosova": "Kosovo",
    "kosovu": "Kosovo",
    "kosovom": "Kosovo",
    "косова": "Косово",
    "косову": "Косово",
    "косовом": "Косово",
    "kine": "Kina",
    "kini": "Kina",
    "kinom": "Kina",
    "кине": "Кина",
    "кини": "Кина",
    "кином": "Кина",
    "rusije": "Rusija",
    "rusiji": "Rusija",
    "rusijom": "Rusija",
    "русије": "Русија",
    "русији": "Русија",
    "русијом": "Русија",
    "ukrajine": "Ukrajina",
    "ukrajini": "Ukrajina",
    "ukrajinom": "Ukrajina",
    "ukrajinu": "Ukrajina",
    "украјине": "Украјина",
    "украјини": "Украјина",
    "украјином": "Украјина",
    "украјину": "Украјина",
    "partizana": "Partizan",
    "partizanu": "Partizan",
    "партизана": "Партизан",
    "партизану": "Партизан",
    "zvezde": "Crvena zvezda",
    "zvezdi": "Crvena zvezda",
    "zvezda": "Crvena zvezda",
}


def normalize_focus_entity_surface(name: str) -> str:
    clean = re.sub(r"\s+", " ", str(name or "").strip())
    if not clean:
        return ""
    normalized = FOCUS_ENTITY_SURFACE_NORMALIZATIONS.get(clean.casefold(), clean)
    if re.fullmatch(r"[A-Za-zÀ-ž\s-]+", normalized) and normalized.islower():
        return normalized.capitalize()
    if normalized and normalized[0].islower():
        return f"{normalized[0].upper()}{normalized[1:]}"
    return normalized


def is_valid_focus_entity(name, entity_type=None):
    clean = normalize_tag_name(name)
    lowered = clean.lower()

    # Strip common news domain extensions for checking noise
    noise_check = re.sub(r"\.(mk|rs|com|net|info|org|press|live)$", "", lowered)

    words = [word for word in re.split(r"\s+", lowered) if word]
    # Also check individual words without extensions
    noise_words = [re.sub(r"\.(mk|rs|com|net|info|org|press|live)$", "", w) for w in words]

    if not clean or len(clean) < 3:
        return False
    if lowered in TAG_NOISE_WORDS or lowered in ENTITY_NOISE_WORDS:
        return False
    if noise_check in SOURCE_NOISE_WORDS or lowered in SOURCE_NOISE_WORDS:
        return False
    if any(word in TAG_NOISE_WORDS or word in ENTITY_NOISE_WORDS for word in words):
        return False
    if any(w in SOURCE_NOISE_WORDS for w in noise_words) or any(w in SOURCE_NOISE_WORDS for w in words):
        return False
    if words and words[0] in TAG_GENERIC_STARTERS:
        return False
    if entity_type and str(entity_type).lower() in {"time", "date", "duration"}:
        return False
    if re.fullmatch(r"\d+", clean):
        return False
    if re.search(r"\b\d{1,2}:\d{2}\b", clean):
        return False
    if clean.count(" ") > 3:
        return False
    if len(words) > 1 and any(len(word) < 3 for word in words):
        return False
    if (
        len(words) == 2
        and words[1] in _DIACRITIC_SPLIT_SUFFIXES
        and not any(ch in "čćšžđ" for ch in lowered)
    ):
        return False
    # Single-token headline verbs / truncated verbal nouns scraped from titles.
    if len(words) == 1:
        token = words[0]
        if re.search(r"(?:nj|нj)$", token, re.IGNORECASE):
            return False
        if len(token) >= 6 and re.search(
            r"(?:ao|ala|alo|ali|ала|ало|али|ао)$", token, re.IGNORECASE
        ):
            return False
        if len(token) >= 6 and re.search(r"(?:aj|ajte|ај|ајте)$", token, re.IGNORECASE):
            return False
    return True


def _count_entity_mentions(entity_name, titles):
    clean = normalize_tag_name(entity_name)
    if not clean:
        return 0
    pattern = re.compile(rf"\b{re.escape(clean)}\b", re.IGNORECASE)
    return sum(1 for title in titles if pattern.search(str(title or "")))


def filter_cluster_tags(tags, limit=10):
    filtered = []
    seen = set()
    for raw in tags or []:
        if isinstance(raw, dict):
            clean = normalize_tag_name(raw.get("name") or raw.get("entity_name") or raw.get("tag"))
            entity_type = raw.get("type") or raw.get("entity_type")
        else:
            clean = normalize_tag_name(raw)
            entity_type = None

        if not is_valid_focus_entity(clean, entity_type):
            continue

        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        filtered.append(clean)
    return filtered[:limit]


def _tokenize_title_terms(text, lemmatize=False):
    tokens = [
        token
        for token in WORD_TOKEN_RE.findall((text or "").lower())
        if token not in STOPWORDS and token not in TAG_NOISE_WORDS and token not in SOURCE_NOISE_WORDS
    ]
    if lemmatize:
        from nlp.text_processing import lemmatize_sr

        return [lemmatize_sr(t) for t in tokens]
    return tokens


_sentence_tokens = _tokenize_title_terms


def _extract_capitalized_phrases(text):
    if not text:
        return []
    pattern = re.compile(
        rf"(?:\b[{LAT_UPPER_CLASS}][{LAT_LOWER_CLASS}]+\b"
        rf"(?:[\s-]+\b[{LAT_UPPER_CLASS}][{LAT_LOWER_CLASS}]+\b){{0,2}})"
    )
    return [match.group(0).strip() for match in pattern.finditer(text)]


def extract_cluster_tags_locally(titles, entity_names=None, sources=None, top_n=8):
    from core.entities import normalize_entity_name
    from nlp.text_processing import lemmatize_sr

    candidates = []
    prioritized_entities = []
    normalized_titles = [str(title or "").strip() for title in titles or [] if str(title or "").strip()]

    for entity in entity_names or []:
        if isinstance(entity, dict):
            name = entity.get("entity_name") or entity.get("name") or entity.get("tag")
            entity_type = entity.get("entity_type") or entity.get("type")
        else:
            name = entity
            entity_type = None
        clean = normalize_tag_name(normalize_entity_name(name))
        if not is_valid_focus_entity(clean, entity_type):
            continue
        mentions = _count_entity_mentions(clean, normalized_titles)
        prioritized_entities.append((mentions, clean))
        candidates.append(entity)

    prioritized_entities.sort(key=lambda item: (item[0], len(item[1].split()), len(item[1])), reverse=True)
    for _mentions, clean in prioritized_entities:
        candidates.insert(0, clean)

    title_tokens = Counter()
    title_bigrams = Counter()
    capitalized = Counter()

    for title in normalized_titles:
        for phrase in _extract_capitalized_phrases(title):
            capitalized[phrase] += 1

        tokens = _tokenize_title_terms(title)
        lemmatized_tokens = [lemmatize_sr(t) for t in tokens]
        title_tokens.update(lemmatized_tokens)

        for left, right in zip(tokens, tokens[1:]):
            if left in TAG_GENERIC_STARTERS or right in TAG_GENERIC_STARTERS:
                continue
            title_bigrams[f"{left} {right}"] += 1

    for phrase, count in capitalized.most_common(12):
        if count >= 1:
            candidates.append(phrase)

    for phrase, count in title_bigrams.most_common(12):
        if count >= 2:
            candidates.append(phrase)

    for token, count in title_tokens.most_common(12):
        if count >= 2 or len(token) >= 7:
            candidates.append(token)

    filtered = filter_cluster_tags(candidates, limit=top_n * 2)
    compact = []
    for candidate in filtered:
        lowered = candidate.casefold()
        candidate_words = lowered.split()
        if any(lowered != other.casefold() and lowered in other.casefold() for other in compact):
            continue
        if any(other.casefold() in lowered and len(other.split()) <= len(candidate_words) for other in compact):
            continue
        compact.append(candidate)
        if len(compact) >= top_n:
            break

    if compact:
        return compact[:top_n]

    return filter_cluster_tags(sources or [], limit=min(top_n, 4))


def _format_common_line_from_phrases(phrases, lang="mk"):
    if not phrases:
        return ""
    # Filter out empty or extremely short phrases
    clean = [str(p).strip() for p in phrases if len(str(p).strip()) > 3]
    if not clean:
        return ""

    if lang == "sr":
        from core.language import transliterate_cyr_to_lat

        clean = [transliterate_cyr_to_lat(p) for p in clean]
        if len(clean) == 1:
            return f"Većina izvora se slaže oko {clean[0]} kao teme u fokusu."
        return f"Većina izvora se slaže oko {', '.join(clean[:-1])} i {clean[-1]} kao tema u fokusu."

    # Default to Macedonian (mk) in Cyrillic
    if len(clean) == 1:
        return f"Повеќето извори се согласуваат околу {clean[0]} како тема во фокус."
    return f"Повеќето извори се согласуваат околу {', '.join(clean[:-1])} i {clean[-1]} како теми во фокус."


def extract_keyphrases_locally(text, top_n=5):
    if not text:
        return []

    kb = _get_keybert()
    if kb is not None:
        try:
            raw = kb.extract_keywords(
                text,
                keyphrase_ngram_range=(1, 3),
                stop_words=None,
                use_mmr=True,
                diversity=0.55,
                top_n=max(top_n * 4, 20),
            )
        except Exception as e:
            log.warning(f"[nlp.keywords] KeyBERT extract failed, falling back: {e}")
            raw = None

        if raw:
            ranked = []
            seen = set()

            for phrase in _extract_capitalized_phrases(text):
                clean = normalize_tag_name(phrase)
                if not clean or not is_valid_focus_entity(clean):
                    continue
                key = clean.casefold()
                if key in seen:
                    continue
                seen.add(key)
                ranked.append(clean)

            for phrase, _score in raw:
                clean = normalize_tag_name(phrase)
                if not clean:
                    continue
                key = clean.casefold()
                if key in seen:
                    continue
                tokens = [t for t in WORD_TOKEN_RE.findall(key) if t]
                if not tokens:
                    continue
                if all(t in STOPWORDS for t in tokens):
                    continue
                if any(t in SOURCE_NOISE_WORDS for t in tokens):
                    continue
                if key in SOURCE_NOISE_WORDS or key in TAG_NOISE_WORDS:
                    continue
                seen.add(key)
                ranked.append(clean)
                if len(ranked) >= top_n:
                    break

            if ranked:
                return ranked[:top_n]

    # Legacy fallback
    words = WORD_TOKEN_RE.findall(text.lower())
    words = [w for w in words if w not in STOPWORDS and w not in SOURCE_NOISE_WORDS and w not in TAG_NOISE_WORDS]

    raw_sentences = re.split(r"[.!?]\s*", text.lower())
    bigrams = []
    trigrams = []
    for sent in raw_sentences:
        sent_words = WORD_TOKEN_RE.findall(sent)
        sent_words = [
            w for w in sent_words if w not in STOPWORDS and w not in SOURCE_NOISE_WORDS and w not in TAG_NOISE_WORDS
        ]
        for i in range(len(sent_words) - 1):
            bigrams.append(f"{sent_words[i]} {sent_words[i+1]}")
        for i in range(len(sent_words) - 2):
            trigrams.append(f"{sent_words[i]} {sent_words[i+1]} {sent_words[i+2]}")

    word_counts = Counter(words)
    bigram_counts = Counter(bigrams)
    trigram_counts = Counter(trigrams)

    candidates = {}
    for word, count in word_counts.items():
        candidates[word] = count
    for bigram, count in bigram_counts.items():
        if count > 1:
            candidates[bigram] = count * 2.5
    for trigram, count in trigram_counts.items():
        if count > 0:
            candidates[trigram] = count * 3.5

    phrase_candidates = []
    for phrase in _extract_capitalized_phrases(text):
        clean = normalize_tag_name(phrase)
        if is_valid_focus_entity(clean):
            phrase_candidates.append(clean)

    ranked = []
    seen = set()
    for phrase, _score in sorted(candidates.items(), key=lambda x: x[1], reverse=True):
        clean = normalize_tag_name(phrase)
        if not clean:
            continue
        key = clean.casefold()
        if key in seen or key in SOURCE_NOISE_WORDS:
            continue
        seen.add(key)
        ranked.append(clean)

    for phrase in phrase_candidates:
        key = phrase.casefold()
        if key in seen:
            continue
        seen.add(key)
        ranked.insert(0, phrase)

    return ranked[:top_n]
