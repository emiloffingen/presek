import re
import threading
from collections import Counter
from trending import STOPWORDS
from nlp.utils import log

_keybert_model = None
_keybert_lock = threading.Lock()
_keybert_unavailable = False

def _get_keybert():
    """Lazy-load KeyBERT once, reusing the shared sentence-transformers model."""
    global _keybert_model, _keybert_unavailable
    if _keybert_unavailable:
        return None
    if _keybert_model is not None:
        return _keybert_model
    with _keybert_lock:
        if _keybert_model is not None:
            return _keybert_model
        try:
            from keybert import KeyBERT
            from embeddings import get_shared_model
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

ENTITY_NOISE_WORDS = {
    "час", "часа", "часот", "минута", "минути", "секунда", "секунди",
    "денес", "денеска", "вчера", "утре", "сега", "вечерва", "утрово", "пладне",
    "јануари", "февруари", "март", "април", "мај", "јуни", "јули",
    "август", "септември", "октомври", "ноември", "декември",
    "слушаме", "гласот", "добронамерните", "овде", "таму",
    "вести", "вест", "извор", "извори", "кластер", "најново", "подготвува",
    "напади", "објави", "изјави", "порача", "соопшти",
    "министерството", "министерот", "министерката", "државниот", "одделот",
    "американскиот", "општата", "сектор", "полициска", "полицаец",
    "тој", "тоа", "прево", "неговите", "нејзините", "нивните", "некои", "кој",
    "што", "како", "каде", "кога", "зошто", "овој", "оваа", "овие", "онаа", "онаков",
    "човекот", "пукаше", "обид", "белата", "куќа", "куќ", "дописници", "дописниц",
    "дали", "нема", "немате", "имате", "биде", "бидат", "може", "можат", "уште", "многу",
    "пренесе", "пренесува", "јави", "јавува", "пишува", "вели", "велат", "стои",
}

TAG_NOISE_WORDS = {
    "вести", "вест", "извор", "извори", "кластер", "македонија", "свет", "инфо",
    "фото", "видео", "денес", "денеска", "утре", "вчера", "сега", "нови", "нова", "ново",
    "објави", "изјави", "порача", "соопшти", "најави", "тврдад", "вели", "велат",
    "министерството", "министерот", "министерката", "државниот", "одделот",
    "американскиот", "општата", "сектор", "полициска", "полицаец",
    "тој", "тоа", "прево", "неговите", "нејзините", "нивните", "некои", "кој",
    "што", "како", "каде", "кога", "зошто", "овој", "оваа", "овие",
    "нападот", "пукање", "гала", "вечерата", "вечера", "пукањето",
    "добронамерните", "добронамерни",
    "човекот", "пукаше", "обид", "белата", "куќа", "куќ", "дописници", "дописниц",
    "шанс", "шанса", "шанси", "немате", "имате", "релации", "трговски", "трговија",
    "начин", "начини", "биде", "бидат", "може", "можат", "вреди", "знам",
    "повеќе", "помалку", "само", "прв", "прва", "втор", "втора", "трет", "трета",
    "ден", "денови", "година", "години", "месец", "месеци", "недела", "недели",
    "време", "промена", "изјава", "најава", "средба", "состанок", "проект", "работа",
    "дел", "околу", "пред", "после", "преку", "против", "меѓу", "сите", "секој",
    "уште", "тука", "пак", "таму", "ваков", "ваква", "онаков", "онаква",
    "дали", "нема", "немате", "имате", "можеби", "веројатно", "сигурно",
    "најголем", "најголема", "најголемо", "најголемите", "последни", "последните",
    "технички", "техничка", "техничко", "поранешен", "поранешна", "поранешно",
    "пулс", "температура", "температури", "контрола", "предлог", "одговор", "реакција",
    "детали", "информација", "информации", "прочитајте", "линк", "преземање", "пренесува",
}

SOURCE_NOISE_WORDS = {
    "reuters", "ap", "afp", "mia", "миа", "mиа", "bbc", "cnn", "dw", "ansa", "tass",
    "associated", "press", "makfax", "макфакс", "тв21", "тв24", "телма", "сител", "канал5",
    "ројтерс", "си-ен-ен", "би-би-си", "дојче веле", "франс прес",
    "plusinfo", "република", "курир", "инфомакс", "фактор", "локално", "бриф", "а1он", "либертас",
}

TAG_GENERIC_STARTERS = {
    "ново", "нова", "нови", "нов", "главно", "главниот", "водечки",
    "утрински", "вечерни", "последни", "последно", "последната",
    "подготвува", "најавува", "повикува", "напади", "напад", "одлука",
    "нападот", "пукање", "уапсен", "уапсени",
    "од", "во", "на", "со", "за", "низ", "без", "врз", "пред", "покрај",
}

def normalize_tag_name(name):
    clean = re.sub(r"\s+", " ", str(name or "").strip(" -–—,.;:!?()[]{}\"'"))
    if not clean:
        return ""
    
    # Handle single character or numeric noise
    if len(clean) < 3 or clean.isdigit():
        return ""

    # 1. Handle specific common typos or bad lemmatizations/truncations
    mapping = {
        "насилството": "Насилство",
        "насилство": "Насилство",
        "општества": "Општество",
        "општеството": "Општество",
        "демократските": "Демократија",
        "белата": "Белата Куќа",
        "куќа": "Белата Куќа",
        "белата куќа": "Белата Куќа",
        "дописниците": "Дописници",
        "место": "", # Generic preposition noise
        "теснецот": "Теснец",
        "нападот": "Напад",
        "пукањето": "Пукање",
        "вечерата": "Вечера",
        "гала": "Гала",
        "атентатот": "Атентат",
        "полицијата": "Полиција",
        "претседателот": "Претседател",
        "претседателството": "Претседателство",
        "владините": "Влада",
        "теснеце": "Теснец",
        "ормускиот": "Ормуз",
        "ормутскиот": "Ормуз",
        "полициј": "Полиција",
        "милијард": "Милијарди",
        "преговор": "Преговори",
        "автомобил": "Автомобили",
        "владин": "Влада",
        "полициск": "Полиција",
        "мицко": "Христијан Мицкоски",
        "мицкоски": "Христијан Мицкоски",
        "мицкоскиот": "Христијан Мицкоски",
        "филипчето": "Венко Филипче",
        "филипче": "Венко Филипче",
        "македонск": "Македонија",
        "американ": "Америка",
        "американски": "Америка",
        "европски": "Европа",
        "руски": "Русија",
        "украински": "Украина",
        "израелски": "Израел",
        "работни": "Работници",
        "работниц": "Работници",
        "техничк": "Технички",
        "последн": "Последно",
        "поранешн": "Поранешен",
    }

    PROTECTED_NAMES = {"македонија", "македонци", "македонски", "македонец", "америка", "американски", "македон"}
    lowered = clean.lower()
    
    if lowered in mapping:
        return mapping[lowered]
        
    if lowered in PROTECTED_NAMES:
        if lowered == "македон": return "Македон"
        if "македон" in lowered: return "Македонија"
        if "америка" in lowered: return "Америка"
        return clean.capitalize()

    # 2. Basic Macedonian Definite Article Stripping (Conservative)
    # Only strip if the word remains long enough and it's a common suffix
    if len(clean) > 7: # Higher threshold to protect words like 'Куќа'
        if clean.endswith("то") or clean.endswith("та"):
             clean = clean[:-2]
        elif clean.endswith("от"):
             clean = clean[:-2] 
        elif clean.endswith("те"):
            clean = clean[:-2]

    # 3. Selective suffix stripping (adjectives -> nouns where clear)
    if len(clean) > 8:
        if not clean.lower().endswith("нија"):
            if not any(lowered.startswith(p) for p in ["македон", "мицкос", "америк", "европ", "русиј", "израел", "украин"]):
                clean = re.sub(r"(овски|евски|скиот|ската|ското|ските)$", "", clean, flags=re.IGNORECASE)
                if clean.lower().endswith("ски") and len(clean) > 5:
                    clean = re.sub(r"ски$", "", clean, flags=re.IGNORECASE)

    # 4. Capitalization fallback
    if re.fullmatch(r"[A-Za-zА-Яа-яЀ-ӿ\s-]+", clean) and clean.islower():
        clean = " ".join(part.capitalize() for part in clean.split(" "))
    
    # 5. Final pass against noise
    if clean.lower() in TAG_NOISE_WORDS or len(clean) < 3:
        return ""
    
    return clean.strip()

def is_valid_focus_entity(name, entity_type=None):
    clean = normalize_tag_name(name)
    lowered = clean.lower()
    words = [word for word in re.split(r"\s+", lowered) if word]

    if not clean or len(clean) < 3:
        return False
    if lowered in TAG_NOISE_WORDS or lowered in ENTITY_NOISE_WORDS:
        return False
    if lowered in SOURCE_NOISE_WORDS:
        return False
    if any(word in TAG_NOISE_WORDS or word in ENTITY_NOISE_WORDS for word in words):
        return False
    if any(word in SOURCE_NOISE_WORDS for word in words):
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
        token for token in re.findall(r"[A-Za-zА-Яа-яЀ-ӿ0-9]{3,}", (text or "").lower())
        if token not in STOPWORDS and token not in TAG_NOISE_WORDS and token not in SOURCE_NOISE_WORDS
    ]
    if lemmatize:
        from nlp.text_processing import lemmatize_mk
        return [lemmatize_mk(t) for t in tokens]
    return tokens

_sentence_tokens = _tokenize_title_terms

def _extract_capitalized_phrases(text):
    if not text:
        return []
    # Explicitly list Cyrillic characters to avoid range errors in some environments
    # Includes standard Russian and specific Macedonian/Balkan Cyrillic characters
    upper = r"[A-ZА-ЯЁЂЃЄЅІЇЈЉЊЋЌЍЎЏ]"
    lower = r"[a-zа-яёђѓєѕіїјљњћќѝўџѐѝ0-9]"
    pattern = re.compile(
        rf"(?:\b{upper}{lower}+\b(?:[\s-]+\b{upper}{lower}+\b){{0,2}})"
    )
    return [match.group(0).strip() for match in pattern.finditer(text)]

def extract_cluster_tags_locally(titles, entity_names=None, sources=None, top_n=8):
    from nlp.text_processing import lemmatize_mk
    from entities import normalize_entity_name
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
        lemmatized_tokens = [lemmatize_mk(t) for t in tokens]
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
        if any(
            other.casefold() in lowered and len(other.split()) <= len(candidate_words)
            for other in compact
        ):
            continue
        compact.append(candidate)
        if len(compact) >= top_n:
            break

    if compact:
        return compact[:top_n]

    return filter_cluster_tags(sources or [], limit=min(top_n, 4))

def _format_common_line_from_phrases(phrases):
    if not phrases:
        return ""
    # Filter out empty or extremely short phrases
    clean = [str(p).strip() for p in phrases if len(str(p).strip()) > 3]
    if not clean:
        return ""
    if len(clean) == 1:
        return f"Повеќето извори се согласуваат околу {clean[0]} како тема во фокус."
    return f"Повеќето извори се согласуваат околу {', '.join(clean[:-1])} и {clean[-1]} како теми во фокус."

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
                tokens = [t for t in re.findall(r"[А-Яа-яЀ-ӿ\w]+", key) if t]
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
    words = re.findall(r'[А-Яа-яЀ-ӿ\w]{4,}', text.lower())
    words = [w for w in words if w not in STOPWORDS and w not in SOURCE_NOISE_WORDS and w not in TAG_NOISE_WORDS]
    
    raw_sentences = re.split(r'[.!?]\s*', text.lower())
    bigrams = []
    trigrams = []
    for sent in raw_sentences:
        sent_words = re.findall(r'[А-Яа-яЀ-ӿ\w]{3,}', sent)
        sent_words = [w for w in sent_words if w not in STOPWORDS and w not in SOURCE_NOISE_WORDS and w not in TAG_NOISE_WORDS]
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
