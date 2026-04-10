import re
import math
import logging
import threading
from collections import Counter

# Reuse stopwords from your trending logic
from trending import STOPWORDS

log = logging.getLogger("presek")

_keybert_model = None
_keybert_lock = threading.Lock()
_keybert_unavailable = False


def _get_keybert():
    """Lazy-load KeyBERT once, reusing the shared sentence-transformers model.
    Returns None if KeyBERT or the embedding model is unavailable."""
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
            log.info("[local_nlp] KeyBERT ready (sharing MiniLM embedding model)")
        except Exception as e:
            log.warning(f"[local_nlp] KeyBERT unavailable, using legacy keyphrases: {e}")
            _keybert_unavailable = True
            return None
        return _keybert_model

# Simple Macedonian Lexicon for Sentiment (Positive / Negative)
# This is a starter list that can be expanded.
SENTIMENT_LEXICON = {
    # Positive - General & Politics
    "добро": 1.0, "одлично": 2.0, "супер": 2.0, "успех": 1.5, "напредок": 1.5,
    "победа": 2.0, "развој": 1.0, "раст": 1.0, "стабилност": 1.5, "безбедност": 1.5,
    "хуманост": 1.5, "правда": 1.5, "слобода": 1.5, "демократија": 1.0, "поддршка": 1.0,
    "помош": 1.0, "решение": 1.5, "просперитет": 2.0, "мир": 2.0, "радост": 1.5,
    "инвестиции": 1.5, "договор": 1.0, "соработка": 1.0, "реформи": 1.0, "награда": 1.5,
    "подобрување": 1.5, "спасени": 2.0, "изградба": 1.0, "позитивно": 1.5,
    "солидарност": 1.5, "донација": 1.5, "триумф": 2.0, "зголемување": 1.0,
    "европски": 0.5, "стандард": 1.0, "интеграција": 1.0, "надеж": 1.5, "одобрено": 1.0,
    
    # Negative - Crime, War, Crisis
    "лошо": -1.0, "катастрофа": -2.0, "криза": -1.5, "проблем": -1.0,
    "скандал": -2.0, "корупција": -2.0, "напад": -1.5, "војна": -2.0, 
    "смрт": -2.0, "убиство": -2.0, "затвор": -1.5, "кражба": -1.5, 
    "криминал": -2.0, "криминалци": -2.0, "неуспех": -1.5, "порази": -1.5, "поразот": -1.5,
    "загуба": -1.5, "критикува": -1.0, "осудува": -1.5, "неправда": -1.5, 
    "хаос": -1.5, "смртност": -2.0, "болест": -1.5, "штета": -1.5, "закана": -1.5, 
    "бомба": -2.0, "несреќа": -2.0, "пожар": -1.5, "судир": -1.5, "повредени": -1.5,
    "жртви": -2.0, "уапсен": -1.0, "уапсени": -1.0, "притвор": -1.0, "осомничен": -1.0,
    "насилство": -2.0, "престрелка": -1.5, "тензии": -1.5, "судење": -0.5,
    "инфлација": -1.5, "поскапување": -1.0, "штрајк": -1.0, "протест": -1.0,
    "оставка": -1.0, "трагедија": -2.0, "уценува": -1.5, "опаснo": -1.5, "опасност": -1.5,
    "загуби": -1.5, "колапс": -2.0, "пад": -1.0, "намалување": -0.5, "влошување": -1.5,
}

ENTITY_NOISE_WORDS = {
    "час", "часа", "часот", "минута", "минути", "секунда", "секунди",
    "денес", "вчера", "утре", "сега", "вечерва", "утрово", "пладне",
    "јануари", "февруари", "март", "април", "мај", "јуни", "јули",
    "август", "септември", "октомври", "ноември", "декември",
    "слушаме", "гласот", "добронамерните", "овде", "таму",
    "вести", "вест", "извор", "извори", "кластер", "најново", "подготвува",
    "напади", "објави", "изјави", "порача", "соопшти",
}

TAG_NOISE_WORDS = {
    "вести", "вест", "извор", "извори", "кластер", "македонија", "свет", "инфо",
    "фото", "видео", "денес", "утре", "вчера", "сега", "нови", "нова", "ново",
}

SOURCE_NOISE_WORDS = {
    "reuters", "ap", "afp", "mia", "mиа", "bbc", "cnn", "dw", "ansa", "tass",
    "associated", "press",
}

TAG_GENERIC_STARTERS = {
    "ново", "нова", "нови", "нов", "главно", "главниот", "водечки",
    "утрински", "вечерни", "последни", "последно", "последната",
}

LOCAL_TRANSLATION_PHRASES = [
    (r"\bbreaking news\b", "итна вест"),
    (r"\blive updates?\b", "следење во живо"),
    (r"\baccording to\b", "според"),
    (r"\bprime minister\b", "премиерот"),
    (r"\bforeign minister\b", "министерот за надворешни работи"),
    (r"\bfinance minister\b", "министерот за финансии"),
    (r"\bdefense minister\b", "министерот за одбрана"),
    (r"\binterior minister\b", "министерот за внатрешни работи"),
    (r"\bhealth minister\b", "министерот за здравство"),
    (r"\bceasefire\b", "прекин на огнот"),
    (r"\binterest rates?\b", "каматни стапки"),
    (r"\bcentral bank\b", "централната банка"),
    (r"\bwhite house\b", "Белата куќа"),
    (r"\beuropean union\b", "Европската Унија"),
    (r"\bunited nations\b", "Обединетите нации"),
    (r"\bsecurity council\b", "Советот за безбедност"),
    (r"\bhuman rights\b", "човекови права"),
    (r"\bclimate change\b", "климатски промени"),
    (r"\bsupreme court\b", "Врховниот суд"),
    (r"\belection commission\b", "изборната комисија"),
]

LOCAL_TRANSLATION_WORDS = {
    "government": "владата",
    "minister": "министерот",
    "president": "претседателот",
    "parliament": "парламентот",
    "opposition": "опозицијата",
    "police": "полицијата",
    "court": "судот",
    "judges": "судиите",
    "judge": "судијата",
    "election": "избори",
    "elections": "избори",
    "voters": "гласачите",
    "vote": "гласање",
    "campaign": "кампања",
    "tariff": "царина",
    "tariffs": "царини",
    "sanction": "санкција",
    "sanctions": "санкции",
    "attack": "напад",
    "attacks": "напади",
    "protest": "протест",
    "protests": "протести",
    "strike": "штрајк",
    "strikes": "штрајкови",
    "package": "пакет",
    "packages": "пакети",
    "measure": "мерка",
    "measures": "мерки",
    "budget": "буџетот",
    "economy": "економијата",
    "inflation": "инфлација",
    "market": "пазарот",
    "markets": "пазарите",
    "company": "компанијата",
    "companies": "компаниите",
    "deal": "договор",
    "agreement": "договор",
    "talks": "разговори",
    "negotiations": "преговори",
    "support": "поддршка",
    "aid": "помош",
    "bill": "законски предлог",
    "law": "законот",
    "report": "извештај",
    "reports": "известува",
    "reported": "објави",
    "says": "вели",
    "said": "изјави",
    "announce": "најавува",
    "announces": "најавува",
    "announced": "најави",
    "warns": "предупредува",
    "warned": "предупреди",
    "approves": "одобрува",
    "approved": "одобри",
    "launches": "почнува",
    "launched": "почна",
    "delays": "одложува",
    "delayed": "одложи",
    "confirms": "потврдува",
    "confirmed": "потврди",
    "denies": "негира",
    "denied": "негираше",
    "urges": "повикува",
    "plans": "планира",
    "plan": "план",
    "new": "нов",
    "latest": "најнов",
    "official": "официјален",
    "officials": "официјални претставници",
    "citizens": "граѓани",
    "crisis": "криза",
    "war": "војна",
    "peace": "мир",
    "military": "војската",
    "troops": "трупи",
    "leader": "лидерот",
    "leaders": "лидерите",
    "meeting": "средба",
    "summit": "самит",
}

LOCAL_TRANSLATION_MONTHS = {
    "january": "јануари",
    "february": "февруари",
    "march": "март",
    "april": "април",
    "may": "мај",
    "june": "јуни",
    "july": "јули",
    "august": "август",
    "september": "септември",
    "october": "октомври",
    "november": "ноември",
    "december": "декември",
    "monday": "понеделник",
    "tuesday": "вторник",
    "wednesday": "среда",
    "thursday": "четврток",
    "friday": "петок",
    "saturday": "сабота",
    "sunday": "недела",
    "today": "денес",
    "tomorrow": "утре",
    "yesterday": "вчера",
}


def normalize_tag_name(name):
    clean = re.sub(r"\s+", " ", str(name or "").strip(" -–—,.;:!?()[]{}\"'"))
    if not clean:
        return ""
    if re.fullmatch(r"[A-Za-zА-Яа-яЀ-ӿ\s-]+", clean) and clean.islower():
        clean = " ".join(part.capitalize() for part in clean.split(" "))
    return clean


def is_valid_focus_entity(name, entity_type=None):
    clean = normalize_tag_name(name)
    lowered = clean.lower()
    words = [word for word in re.split(r"\s+", lowered) if word]

    if not clean or len(clean) < 3:
        return False
    if lowered in TAG_NOISE_WORDS:
        return False
    if lowered in SOURCE_NOISE_WORDS:
        return False
    if any(word in TAG_NOISE_WORDS for word in words):
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


def _tokenize_title_terms(text):
    return [
        token for token in re.findall(r"[A-Za-zА-Яа-яЀ-ӿ0-9]{3,}", (text or "").lower())
        if token not in STOPWORDS and token not in TAG_NOISE_WORDS and token not in SOURCE_NOISE_WORDS
    ]


# Alias — _sentence_tokens is used by the summarizer and similarity helpers;
# semantically identical to title-term tokenization (filters stopwords + noise).
_sentence_tokens = _tokenize_title_terms


def _extract_capitalized_phrases(text):
    if not text:
        return []
    # Uppercase class: Latin A-Z + Cyrillic Ѐ-Я (U+0400-U+042F)
    # Lowercase class: Latin a-z + Cyrillic а-я plus extended lowercase ѐ-ӿ
    # The earlier pattern used [Ѐ-ӿ] in the "uppercase" class which also
    # matched lowercase Cyrillic, so the whole capitalization constraint
    # was silently disabled and lowercase phrases polluted the results.
    upper = r"[A-ZЀ-Я]"
    lower = r"[a-zа-я0-9ѐ-ӿ]"
    pattern = re.compile(
        rf"(?:\b{upper}{lower}+\b(?:[\s-]+\b{upper}{lower}+\b){{0,2}})"
    )
    return [match.group(0).strip() for match in pattern.finditer(text)]


def extract_cluster_tags_locally(titles, entity_names=None, sources=None, top_n=8):
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
        clean = normalize_tag_name(name)
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
        title_tokens.update(tokens)
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

# Negation words in Macedonian
NEGATIONS = {"не", "ниту", "никако", "без", "престана", "прекина", "против"}

def analyze_sentiment_locally(text):
    """
    Returns a score between -2.0 and 2.0 based on keyword frequency.
    Improved with negation detection.
    """
    if not text: return 0.0
    
    words = re.findall(r'[А-Яа-яЀ-ӿ\w]{2,}', text.lower())
    score = 0.0
    matches = 0
    negate_next = False
    
    for w in words:
        if w in NEGATIONS:
            negate_next = True
            continue
            
        if w in SENTIMENT_LEXICON:
            val = SENTIMENT_LEXICON[w]
            if negate_next:
                val = -val * 0.8 # Flip and slightly damp
                negate_next = False
            
            score += val
            matches += 1
        else:
            # Reset negation if no sentiment word follows immediately
            negate_next = False
            
    if matches == 0: return 0.0
    
    # Normalize by matches but cap at 2.0
    final_score = score / matches
    return max(-2.0, min(2.0, final_score))

def extract_keyphrases_locally(text, top_n=5):
    """
    Extract high-value phrases. Prefers KeyBERT (semantic, via shared MiniLM)
    and falls back to the legacy frequency+co-occurrence heuristic if KeyBERT
    is unavailable. Results are always filtered through the project's noise
    and validity filters so source brands ("Reuters", "AP") stay out.
    """
    if not text:
        return []

    kb = _get_keybert()
    if kb is not None:
        try:
            # Ask for a generous candidate pool; we'll filter + dedupe below.
            raw = kb.extract_keywords(
                text,
                keyphrase_ngram_range=(1, 3),
                stop_words=None,  # Macedonian — no built-in list, we filter manually
                use_mmr=True,
                diversity=0.55,
                top_n=max(top_n * 4, 20),
            )
        except Exception as e:
            log.warning(f"[local_nlp] KeyBERT extract failed, falling back: {e}")
            raw = None

        if raw:
            ranked = []
            seen = set()

            # Capitalized phrases get first claim on the slots (same rule
            # the legacy path uses — named entities beat common nouns).
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
                # Filter stopwords / source brands / tag noise, matching
                # the guarantees of the legacy implementation.
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
            # If KeyBERT returned nothing usable, drop through to legacy.

    # --- Legacy fallback: frequency + co-occurrence ---
    # Simple word counting excluding stopwords and source-brand noise
    words = re.findall(r'[А-Яа-яЀ-ӿ\w]{4,}', text.lower())
    words = [w for w in words if w not in STOPWORDS and w not in SOURCE_NOISE_WORDS and w not in TAG_NOISE_WORDS]
    
    # Multi-word candidate search (Bigrams & Trigrams)
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
    
    # Combine and score (bias towards bigrams and trigrams)
    candidates = {}
    for word, count in word_counts.items():
        candidates[word] = count
    for bigram, count in bigram_counts.items():
        if count > 1: # Only if it appears twice
            candidates[bigram] = count * 2.5
    for trigram, count in trigram_counts.items():
        if count > 0: # Even once might be significant if words are rare, but let's stick to count > 0, score * 3.5
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


def _format_common_line_from_phrases(phrases):
    clean = [normalize_tag_name(phrase).lower() for phrase in phrases if normalize_tag_name(phrase)]
    clean = [phrase for phrase in clean if phrase not in SOURCE_NOISE_WORDS and phrase not in TAG_NOISE_WORDS]
    if not clean:
        return ""
    if len(clean) == 1:
        return f"Повеќето извори се согласуваат дека во фокус е {clean[0]}."
    if len(clean) == 2:
        return f"Повеќето извори се согласуваат дека во фокус се {clean[0]} и {clean[1]}."
    return f"Повеќето извори се согласуваат дека во фокус се {', '.join(clean[:2])}, како и {clean[2]}."


def _jaccard_similarity(sent1, sent2):
    """Calculates word-level overlap similarity between two sentences."""
    words1 = set(_sentence_tokens(sent1))
    words2 = set(_sentence_tokens(sent2))
    if not words1 or not words2: return 0.0
    return len(words1 & words2) / len(words1 | words2)

def synthesize_locally(articles, sentence_count=4, topic=None):
    """
    Sophisticated Local Synthesis Engine.
    Implements Narrative Construction: Anchor -> Detail -> Action/Reaction.
    """
    if not articles: return ""
    
    all_candidates = []
    source_counts = {}
    
    # 1. Extraction & Pre-scoring
    for art in articles:
        src = art.get('source', 'Извор')
        text = f"{art.get('title', '')}. {art.get('description', '')}"
        # Split but keep track of position
        raw_sents = re.split(r'(?<=[.!?])\s+', text)
        for idx, s in enumerate(raw_sents):
            clean_s = _normalize_summary_sentence(s)
            if not clean_s or _is_noisy_summary_sentence(clean_s):
                continue
            
            # Identify "Action" verbs in Macedonian
            is_action = any(v in clean_s.lower() for v in ["изјави", "најави", "предупреди", "порача", "истакна", "повика", "одлучи"])
            
            # Base heuristic score
            s_words = _sentence_tokens(clean_s)
            if not s_words: continue
            
            entities = set(_extract_capitalized_phrases(clean_s))
            
            # Calculate value
            val_score = len(s_words) * 0.1 # Density
            val_score += 0.8 if idx == 0 else 0.0 # Lead priority
            val_score += 0.6 if is_action else 0.0 # Action priority
            val_score += 0.5 if _extract_number_tokens(clean_s) else 0.0 # Data priority
            val_score += len(entities) * 0.4 # Entity density
            
            all_candidates.append({
                "text": clean_s,
                "score": val_score,
                "entities": entities,
                "source": src,
                "is_action": is_action
            })

    if not all_candidates: return ""

    # Sort candidates by raw score
    all_candidates.sort(key=lambda x: x['score'], reverse=True)

    # 2. Greedy Narrative Selection
    selected = []
    used_entities = set()
    used_sources = set()
    
    for _ in range(sentence_count):
        best_candidate = None
        best_boosted_score = -1.0
        
        for cand in all_candidates:
            # Skip if already selected or too redundant
            if any(_jaccard_similarity(cand['text'], s['text']) > 0.4 for s in selected):
                continue
            
            # Calculate Dynamic Boosts
            diversity_boost = 1.3 if cand['source'] not in used_sources else 1.0
            new_entity_boost = 1.0 + (len(cand['entities'] - used_entities) * 0.3)
            
            # Narrative Flow: 
            # - First sentence should be an "Anchor" (high raw score)
            # - Last sentences should favor "Action/Reaction"
            flow_boost = 1.0
            if len(selected) == 0: flow_boost = 1.2
            if len(selected) >= 2 and cand['is_action']: flow_boost = 1.4
            
            boosted_score = cand['score'] * diversity_boost * new_entity_boost * flow_boost
            
            if boosted_score > best_boosted_score:
                best_boosted_score = boosted_score
                best_candidate = cand
        
        if best_candidate:
            selected.append(best_candidate)
            used_entities.update(best_candidate['entities'])
            used_sources.add(best_candidate['source'])
        else:
            break

    # 3. Final Formatting
    # Sort selected back to a natural flow if needed, but here greedy order usually works
    res = []
    for s in selected:
        txt = s['text']
        # Capitalize first letter if not
        if txt and txt[0].islower():
            txt = txt[0].upper() + txt[1:]
        res.append(f"• {txt}")
        
    return "\n".join(res)


def _normalize_summary_sentence(sentence):
    text = re.sub(r"\s+", " ", str(sentence or "")).strip()
    text = re.sub(r"^[•*\-\u2022]+\s*", "", text)
    return text


def rewrite_to_macedonian_locally(text):
    """
    Deterministic, low-cost rewrite for short news text.
    It is not a full translation engine; it normalizes already-Macedonian text
    and converts common English news vocabulary into usable Macedonian copy.
    """
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return text

    text = re.sub(r"^\s*translate(?: the following)?\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*summary\s*:\s*", "", text, flags=re.IGNORECASE)

    # If the text is already mostly Cyrillic, just normalize presentation.
    cyrillic_chars = len(re.findall(r"[А-Яа-яЀ-ӿ]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    if cyrillic_chars >= max(8, latin_chars):
        normalized = re.sub(r"\s+", " ", text).strip(" -–—")
        return normalized[:420]

    working = f" {text} "
    for pattern, replacement in LOCAL_TRANSLATION_PHRASES:
        working = re.sub(pattern, replacement, working, flags=re.IGNORECASE)

    def _replace_word(match):
        word = match.group(0)
        lowered = word.lower()
        replacement = LOCAL_TRANSLATION_MONTHS.get(lowered) or LOCAL_TRANSLATION_WORDS.get(lowered)
        if not replacement:
            return word
        if word.isupper():
            return replacement.upper()
        if word[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement

    working = re.sub(r"\b[A-Za-z][A-Za-z'-]*\b", _replace_word, working)
    working = re.sub(r"\s+", " ", working).strip()

    working = re.sub(r"\bthe\b", "", working, flags=re.IGNORECASE)
    working = re.sub(r"\ba\b", "", working, flags=re.IGNORECASE)
    working = re.sub(r"\ban\b", "", working, flags=re.IGNORECASE)
    working = re.sub(r"\s+,", ",", working)
    working = re.sub(r"\s+\.", ".", working)
    working = re.sub(r"\s{2,}", " ", working).strip(" -–—")

    if not re.search(r"[А-Яа-яЀ-ӿ]", working):
        return text[:420]

    if not re.search(r"[.!?]$", working):
        working += "."

    return working[:420]


def _is_noisy_summary_sentence(sentence):
    text = _normalize_summary_sentence(sentence)
    if not text:
        return True
    if len(text) < 28:
        return True
    lowered = text.lower()
    if lowered.startswith(("фото:", "видео:", "gallery:", "галерија:", "коментар:", "реклама:")):
        return True
    if text.count("#") >= 2:
        return True
    return False

def summarize_locally(text, sentence_count=3, topic=None):
    """
    Non-AI summarizer for news-like text.
    Improved with Topic-Awareness.
    """
    if not text or len(text) < 100:
        return text

    sentences = [
        _normalize_summary_sentence(sentence)
        for sentence in re.split(r'(?<=[.!?])\s+', text)
    ]
    sentences = [sentence for sentence in sentences if sentence]
    if len(sentences) <= sentence_count:
        return text

    title_like_terms = set(_sentence_tokens(sentences[0]))
    words = _sentence_tokens(text)
    word_freq = Counter(words)
    if not word_freq:
        return ". ".join(sentences[:sentence_count])

    max_freq = max(word_freq.values())
    for word in word_freq:
        word_freq[word] = word_freq[word] / max_freq

    # Topic-specific keywords to boost
    topic_boost_words = set()
    if topic == "Економија":
        topic_boost_words = {"денари", "евра", "процент", "милиони", "буџет", "плата", "цени", "инфлација", "берза"}
    elif topic == "Политика":
        topic_boost_words = {"министер", "претседател", "собрание", "закон", "партија", "лидер", "влада", "избори"}
    elif topic == "Спорт":
        topic_boost_words = {"натпревар", "гол", "победа", "првенство", "клуб", "лига", "фудбал", "кошарка"}
    elif topic == "Криминал":
        topic_boost_words = {"полиција", "апсење", "убиство", "суд", "обвинителство", "затвор", "напад"}

    sentence_scores = {}
    for i, sentence in enumerate(sentences):
        sentence_words = _sentence_tokens(sentence)
        if not sentence_words:
            continue

        score = sum(word_freq.get(word, 0) for word in sentence_words)
        overlap = len(set(sentence_words) & title_like_terms)
        number_bonus = 0.5 if _extract_number_tokens(sentence) else 0.0
        lead_bonus = 1.8 / (i + 1)
        density_bonus = min(len(sentence_words), 24) / 24
        proper_noun_bonus = len(_extract_capitalized_phrases(sentence)) * 0.3
        
        # Topic alignment bonus
        topic_bonus = 0.0
        if topic_boost_words:
            matched_topic_words = len(set(sentence_words) & topic_boost_words)
            topic_bonus = matched_topic_words * 0.5

        if _is_noisy_summary_sentence(sentence):
            score *= 0.1

        if len(sentence) > 280:
            score *= 0.6

        score += (overlap * 0.5) + number_bonus + lead_bonus + density_bonus + proper_noun_bonus + topic_bonus
        sentence_scores[i] = score

    top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:sentence_count]
    top_indices.sort()

    summary = []
    seen = set()
    for idx in top_indices:
        sentence = sentences[idx].strip()
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        summary.append(sentence)

    if not summary:
        summary = [sentence for sentence in sentences[:sentence_count] if not _is_noisy_summary_sentence(sentence)]

    return " ".join(summary)


def summarize_article_fallback(title, description=None, topic=None):
    parts = [str(title or "").strip(), str(description or "").strip()]
    text = ". ".join([part for part in parts if part])
    summary = summarize_locally(text, sentence_count=2, topic=topic).strip()
    summary = re.sub(r'^[⚪🟢🔴]\s*', '', summary, flags=re.UNICODE)
    summary = re.sub(r'#[^\s#]+', '', summary)
    summary = re.sub(r'\s+', ' ', summary).strip()
    if summary:
        return summary[:420]
    return str(title or "").strip()


def _normalize_articles_for_local_use(articles):
    normalized = []
    for article in articles or []:
        normalized.append({
            "title": str(article.get("title") or "").strip(),
            "description": str(article.get("description") or "").strip(),
            "source": str(article.get("source") or "Извор").strip(),
            "link": article.get("link"),
            "created_at": article.get("created_at"),
            "category": article.get("category"),
        })
    return [article for article in normalized if article["title"]]


def _extract_terms(text):
    return [
        term for term in re.findall(r"[A-Za-zА-Яа-яЀ-ӿ0-9]{3,}", (text or "").lower())
        if term not in STOPWORDS
    ]


def _extract_number_tokens(text):
    return re.findall(r"\b\d+(?::\d+)?(?:[%.,]\d+)?\b", str(text or ""))


def _join_fragments(parts):
    clean = [str(part or "").strip(" .,;:") for part in parts if str(part or "").strip(" .,;:")]
    return "; ".join(clean)


def _source_list(articles, limit=3):
    names = [str(article.get("source") or "Извор").strip() for article in articles[:limit]]
    return ", ".join(name for name in names if name)


def compare_cluster_sources(articles):
    articles = _normalize_articles_for_local_use(articles)
    if not articles:
        return {"common_line": "", "difference_points": [], "open_points": []}

    uncertainty_markers = (
        "тврди", "според", "непотвр", "навод", "се очекува", "може",
        "би мож", "засега", "се уште", "се уште", "се развива",
    )

    all_terms = Counter()
    article_term_sets = []
    article_texts_lower = []
    title_pairs = []
    number_map = {}
    uncertain_sources = []

    for article in articles:
        combined = " ".join([article["title"], article["description"]]).strip()
        terms = set(_extract_terms(combined))
        article_term_sets.append(terms)
        all_terms.update(terms)
        article_texts_lower.append(combined.lower())

        title = article["title"]
        if title:
            title_pairs.append((article["source"], title))

        for number in _extract_number_tokens(combined):
            number_map.setdefault(number, set()).add(article["source"])

        lowered = combined.lower()
        if any(marker in lowered for marker in uncertainty_markers):
            uncertain_sources.append(article["source"])

    threshold = max(2, math.ceil(len(articles) / 2))
    common_terms = [term for term, count in all_terms.most_common(8) if count >= threshold and term not in SOURCE_NOISE_WORDS]

    # Pool all articles, extract keyphrases once, then keep only the
    # phrases that actually appear (as a substring) in `threshold` or more
    # of the per-article texts. This is robust against KeyBERT returning
    # slightly different surface forms between articles.
    pooled_text = " ".join(a["title"] + ". " + a["description"] for a in articles)
    candidate_phrases = extract_keyphrases_locally(pooled_text, top_n=12)
    common_phrases = []
    for phrase in candidate_phrases:
        if not phrase or " " not in phrase:
            continue  # only multi-word phrases qualify here
        needle = phrase.lower()
        hits = sum(1 for txt in article_texts_lower if needle in txt)
        if hits >= threshold:
            common_phrases.append(phrase)
    common_line = ""
    if common_phrases:
        common_line = _format_common_line_from_phrases(common_phrases[:3])
    elif common_terms:
        common_line = "Повеќето извори се согласуваат околу: " + ", ".join(common_terms[:4]) + "."

    difference_points = []
    unique_titles = []
    seen_titles = set()
    for source, title in title_pairs:
        key = title.casefold()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        unique_titles.append((source, title))
    if len(unique_titles) >= 2:
        lead_source, lead_title = unique_titles[0]
        second_source, second_title = unique_titles[1]
        difference_points.append(
            f"{lead_source} најдиректно го формулира развојот како „{lead_title}“, додека {second_source} повеќе нагласува „{second_title}“."
        )

    conflicting_numbers = []
    for number, sources in number_map.items():
        if len(sources) >= 1:
            conflicting_numbers.append((number, sorted(sources)))
    distinct_numbers = [item for item in conflicting_numbers if len(item[1]) >= 1]
    if len(distinct_numbers) >= 2:
        top_numbers = []
        for number, sources in distinct_numbers[:3]:
            top_numbers.append(f"{number} ({', '.join(sources[:2])})")
        difference_points.append(
            "Изворите не ги нагласуваат истите бројки или рокови: " + ", ".join(top_numbers) + "."
        )

    if len(articles) >= 2 and article_term_sets:
        exclusive_parts = []
        first_terms = article_term_sets[0]
        second_terms = article_term_sets[1]
        first_unique = [term for term in first_terms if term not in second_terms][:2]
        second_unique = [term for term in second_terms if term not in first_terms][:2]
        if first_unique or second_unique:
            if first_unique:
                exclusive_parts.append(f"{articles[0]['source']} повеќе отвора: {', '.join(first_unique)}")
            if second_unique:
                exclusive_parts.append(f"{articles[1]['source']} повеќе отвора: {', '.join(second_unique)}")
        if exclusive_parts:
            difference_points.append(_join_fragments(exclusive_parts) + ".")

    open_points = []
    if uncertain_sources:
        source_list = ", ".join(dict.fromkeys(uncertain_sources))
        open_points.append(
            f"Дел од тврдењата и понатаму се формулирани како развој во тек или непотврдена најава, особено кај {source_list}."
        )
    if len(number_map) >= 2:
        open_points.append("Не е целосно јасно кои бројки, рокови или размери ќе останат конечни по следните потврди.")
    if not open_points and len(articles) >= 2:
        open_points.append("Главната линија е јасна, но следните чекори, реакциите и конечните последици сè уште се развиваат.")

    deduped_differences = []
    seen = set()
    for item in difference_points:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped_differences.append(item)

    deduped_open = []
    seen = set()
    for item in open_points:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped_open.append(item)

    return {
        "common_line": common_line,
        "difference_points": deduped_differences[:3],
        "open_points": deduped_open[:2],
    }


def synthesize_cluster_fallback(articles):
    articles = _normalize_articles_for_local_use(articles)
    if not articles:
        return {"summary": "", "perspectives": []}

    lead = articles[0]
    descriptions = [article["description"] for article in articles if article["description"]]
    combined_text = " ".join([lead["title"], *descriptions[:4]])
    context_summary = summarize_locally(combined_text, sentence_count=3).strip()
    comparison = compare_cluster_sources(articles)

    summary_lines = [f"• Што се случува: {lead['title']}"]
    if comparison["common_line"]:
        common_line = re.sub(r"^Повеќето извори се согласуваат околу:\s*", "", comparison["common_line"]).strip()
        summary_lines.append(f"• Заедничка линија: {common_line}")
    summary_lines.append(
        f"• Покриеност: темата ја следат {len(articles)} извори, со водечки сигнали од {_source_list(articles)}."
    )
    follow_line = ""
    if context_summary:
        summary_lines.append(f"• Контекст: {context_summary}")
    if comparison["open_points"]:
        follow_line = f"• Што останува отворено: {' '.join(comparison['open_points'][:1])}"
    elif descriptions:
        next_line = summarize_locally(descriptions[0], sentence_count=1).strip() or descriptions[0][:220].rstrip(" .,;:")
        follow_line = f"• Следно за следење: {next_line}."

    if follow_line:
        if len(summary_lines) >= 4:
            summary_lines = summary_lines[:3]
        summary_lines.append(follow_line)

    perspectives = []
    if comparison["common_line"]:
        perspectives.append({
            "angle": "Заедничка линија",
            "content": re.sub(r"^Повеќето извори се согласуваат околу:\s*", "", comparison["common_line"]).strip(),
        })

    if comparison["difference_points"]:
        perspectives.append({
            "angle": "Различни акценти",
            "content": " ".join(comparison["difference_points"][:2]),
        })

    if comparison["open_points"]:
        perspectives.append({
            "angle": "Што останува отворено",
            "content": " ".join(comparison["open_points"]),
        })

    return {
        "summary": "\n".join(summary_lines[:4]),
        "perspectives": perspectives[:3],
    }


def generate_daily_brief_fallback(clusters):
    if not clusters:
        return "## Дневен Брифинг\n\nНема доволно достапни вести за автоматски локален брифинг."

    lines = ["## Што го движи денот", ""]
    intro_titles = [str(item.get("title") or "").strip() for item in clusters[:3] if str(item.get("title") or "").strip()]
    if intro_titles:
        lines.append(
            "Денот најсилно се врти околу "
            + ", ".join(intro_titles[:2])
            + (f", а во поширокиот фокус влегува и {intro_titles[2]}." if len(intro_titles) > 2 else ".")
        )
        lines.append("")

    difference_lines = []
    watch_lines = []
    for index, cluster in enumerate(clusters[:4], start=1):
        title = str(cluster.get("title") or "").strip()
        source = str(cluster.get("source") or "Извор").strip()
        topic = str(cluster.get("topic") or cluster.get("category") or "Вести").strip()
        description = str(cluster.get("description") or "").strip()
        summary = summarize_locally(f"{title}. {description}", sentence_count=2).strip()
        source_count = int(cluster.get("source_count") or 1)
        open_point = str(cluster.get("open_point") or "").strip()
        difference_point = str(cluster.get("difference_point") or "").strip()

        lines.append(f"### {index}. {title}")
        lines.append(f"- Што се менува: {summary or title}")
        lines.append(f"- Зошто е важно: Темата е во фокусот на {topic.lower()} покривањето и во моментов ја следат {source_count} извори, со водечки сигнал од {source}.")
        lines.append("")

        if difference_point:
            difference_lines.append(f"- {difference_point}")
        elif source_count >= 3:
            difference_lines.append(f"- Кај {title[:90]} најмногу се разликува акцентот меѓу изворите, додека главната линија останува слична.")
        if open_point:
            watch_lines.append(f"- {open_point}")
        else:
            watch_lines.append(f"- Следен сигнал за следење е нова потврда, реакција или институционален чекор околу: {title[:90]}.")

    lines.append("## Каде се разликува известувањето")
    lines.extend(difference_lines[:3] or ["- Повеќето водечки приказни носат слична главна линија, но различен акцент, рамка или избор на детали."])
    lines.append("")
    lines.append("## Што да се следи понатаму")
    lines.extend(watch_lines[:3] or ["- Следните часови најмногу ќе зависат од нови потврди, официјални реакции и дополнителни бројки."])
    lines.append("")
    lines.append("**Напомена**")
    lines.append("Овој брифинг е составен локално од најважните рангирани кластери кога автоматскиот брифинг не е достапен.")
    return "\n".join(lines).strip()


def answer_cluster_question_locally(question, articles, synthesis="", perspectives=None):
    articles = _normalize_articles_for_local_use(articles)
    if not question or not articles:
        return None

    lowered = question.lower()
    lead = articles[0]
    citations = articles[:2]
    comparison = compare_cluster_sources(articles)
    related_questions = [
        "Како се разликуваат изворите во известувањето?",
        "Што сè уште не е потврдено?",
        "Кој е следниот важен чекор во оваа приказна?",
    ]

    if any(token in lowered for token in ["разлику", "извори", "перспектив"]):
        emphasis = comparison["difference_points"] or [f"{article['source']} го истакнува „{article['title']}“" for article in articles[:3]]
        return {
            "answer": "Изворите најмногу се разликуваат во акцентот и формулацијата. " + " ".join(emphasis[:2]),
            "citations": citations,
            "related_questions": related_questions,
            "confidence": "medium",
        }

    if any(token in lowered for token in ["нејасно", "непотврдено", "отворено", "што не се знае"]):
        answer = "Најотворени остануваат следните детали. "
        open_line = " ".join(comparison["open_points"][:2]) or "Во достапните извори нема целосна слика за сите детали. Најјасно е основното случување, додека последиците, реакциите и следните чекори сè уште се развиваат."
        if synthesis:
            answer = f"{answer}{open_line} Тековниот преглед сугерира: {summarize_locally(synthesis, sentence_count=1)}"
        else:
            answer = f"{answer}{open_line}"
        return {
            "answer": answer,
            "citations": citations,
            "related_questions": related_questions,
            "confidence": "medium",
        }

    if any(token in lowered for token in ["најваж", "што е ново", "што се случ", "главно", "што има"]):
        answer = f"Во овој момент, главниот развој е: {lead['title']}."
        if lead["description"]:
            answer += f" {summarize_locally(lead['description'], sentence_count=1)}"
        if comparison["common_line"]:
            common_line = re.sub(r"^Повеќето извори се согласуваат околу:\s*", "", comparison["common_line"]).strip()
            answer += f" Заедничката линија е: {common_line}"
        answer += f" Темата во моментов е покриена од {len(articles)} извори."
        return {
            "answer": answer,
            "citations": citations,
            "related_questions": related_questions,
            "confidence": "high",
        }

    terms = set(_extract_terms(question))
    if terms:
        scored = []
        for article in articles:
            haystack_terms = set(_extract_terms(" ".join([article["title"], article["description"]])))
            scored.append((len(terms & haystack_terms), article))
        scored.sort(key=lambda item: item[0], reverse=True)
        top = [article for score, article in scored if score > 0][:2]
        if top:
            answer = f"Најрелевантно за вашето прашање е: {top[0]['title']}."
            if top[0]["description"]:
                answer += f" {summarize_locally(top[0]['description'], sentence_count=1)}"
            return {
                "answer": answer,
                "citations": top,
                "related_questions": related_questions,
                "confidence": "medium",
            }

    return None


def build_citation_snippet(article):
    title = str((article or {}).get("title") or "").strip()
    description = str((article or {}).get("description") or "").strip()
    if description:
        snippet = summarize_locally(description, sentence_count=1).strip()
        if snippet:
            return snippet[:220]
    return title[:220]


def build_structured_answer_sections(answer, articles=None, synthesis="", perspectives=None):
    answer = str(answer or "").strip()
    articles = _normalize_articles_for_local_use(articles)
    perspectives = perspectives or []
    comparison = compare_cluster_sources(articles)

    sentences = [
        sentence.strip()
        for sentence in re.split(r'(?<=[.!?])\s+', answer)
        if sentence.strip()
    ]
    uncertainty_markers = (
        "не е потврдено", "не е јасно", "нејасно", "непотврдено",
        "не се знае", "отворено", "се развива", "засега",
    )

    confirmed_points = []
    unclear_points = []

    for sentence in sentences:
        lowered = sentence.lower()
        if any(marker in lowered for marker in uncertainty_markers):
            unclear_points.append(sentence)
        else:
            confirmed_points.append(sentence)

    if not confirmed_points and sentences:
        confirmed_points = sentences[:2]

    if not unclear_points:
        if comparison["open_points"]:
            unclear_points.extend(comparison["open_points"][:2])
        elif perspectives:
            unclear_points.append("Изворите нудат различни акценти, но не даваат целосна слика за сите следни чекори.")
        elif synthesis:
            unclear_points.append("Достапниот контекст ја објаснува главната линија, но не ги затвора сите отворени детали.")

    source_differences = ""
    if perspectives:
        top = []
        for item in perspectives[:2]:
            angle = str(item.get("angle") or "").strip()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            if angle:
                top.append(f"{angle}: {content}")
            else:
                top.append(content)
        if top:
            source_differences = " ".join(top)[:360]

    if not source_differences and comparison["difference_points"]:
        source_differences = " ".join(comparison["difference_points"])[:360]

    if not source_differences and len(articles) >= 2:
        lead = articles[0]
        second = articles[1]
        lead_title = str(lead.get("title") or "").strip()
        second_title = str(second.get("title") or "").strip()
        if lead_title and second_title and lead_title != second_title:
            source_differences = (
                f"{lead['source']} најдиректно го формулира развојот како „{lead_title}“, "
                f"додека {second['source']} повеќе нагласува „{second_title}“."
            )[:360]
        else:
            source_differences = (
                f"{lead['source']} повеќе се држи до водечкиот развој, "
                f"додека {second['source']} додава контекст, реакција или поширока последица."
            )

    return {
        "confirmed_points": confirmed_points[:3],
        "unclear_points": unclear_points[:2],
        "source_differences": source_differences,
    }

def generate_local_placeholder(cluster_id, title, category="Вести"):
    """
    Generates a stylized SVG placeholder and returns the SVG string.
    Category-aware colors and patterns.
    """
    # Editorial, category-aware palette
    colors = {
        "Македонија": "#a63d40",
        "Балкан": "#3d6b63",
        "Европа": "#3f7d8a",
        "Америка": "#3e6282",
        "Свет": "#5f556f",
        "Спорт": "#b36b24",
        "Технологија": "#3e4954",
        "Економија": "#456a4f",
        "default": "#5f6470",
    }

    bg_color = colors.get(category, colors["default"])
    title = re.sub(r"\s+", " ", (title or "").strip())
    title = title[:140] + "..." if len(title) > 140 else title

    def escape(text):
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def wrap_lines(text, max_chars=22, max_lines=4):
        if not text:
            return ["Преглед на веста"]
        words = text.split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) == max_lines - 1:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)

        remaining_words = words[len(" ".join(lines).split()):]
        if remaining_words and lines:
            lines[-1] = lines[-1][: max(0, max_chars - 1)].rstrip(" .,") + "…"
        return lines[:max_lines]

    lines = wrap_lines(title)
    title_svg = []
    y = 176
    for line in lines:
        title_svg.append(
            f'<text x="400" y="{y}" font-family="serif" text-anchor="middle" '
            f'font-size="44" font-weight="700" letter-spacing="-1.15" fill="#162132">{escape(line)}</text>'
        )
        y += 52

    subtitle = f"{category.upper()} / ПРЕСЕК"
    pattern_seed = len(title) % 4
    pattern_svg = [
        '<circle cx="690" cy="84" r="112" fill="#fffdf7" fill-opacity="0.24" /><circle cx="612" cy="148" r="42" fill="#fffdf7" fill-opacity="0.18" />',
        '<path d="M558 44 L770 44 L636 214 Z" fill="#fffdf7" fill-opacity="0.18" /><rect x="598" y="108" width="140" height="12" fill="#162132" fill-opacity="0.12" />',
        '<rect x="564" y="40" width="188" height="166" rx="28" fill="#fffdf7" fill-opacity="0.17" /><circle cx="648" cy="122" r="58" fill="#162132" fill-opacity="0.08" />',
        '<path d="M566 62 C612 26, 710 26, 752 78 C706 116, 614 122, 566 62 Z" fill="#fffdf7" fill-opacity="0.18" /><rect x="584" y="134" width="160" height="46" fill="#fffdf7" fill-opacity="0.12" />',
    ][pattern_seed]

    svg = f"""<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#f8f2e7" />
      <stop offset="58%" stop-color="#fdfbf7" />
      <stop offset="100%" stop-color="{bg_color}" />
    </linearGradient>
    <linearGradient id="ink" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#162132" stop-opacity="0.92" />
      <stop offset="100%" stop-color="#314055" stop-opacity="0.72" />
    </linearGradient>
  </defs>

  <rect width="100%" height="100%" fill="url(#bg)" />
  <rect width="100%" height="100%" fill="#f8f5ef" fill-opacity="0.18" />
  <rect x="26" y="26" width="748" height="398" fill="none" stroke="#162132" stroke-opacity="0.12" />
  <rect x="42" y="42" width="716" height="366" fill="#fffdf9" fill-opacity="0.42" />
  <line x1="250" y1="130" x2="550" y2="130" stroke="#314055" stroke-opacity="0.5" stroke-width="2.5" />

  {"".join(title_svg)}

  <g>
    {pattern_svg}
  </g>
  <line x1="100" y1="372" x2="700" y2="372" stroke="#162132" stroke-opacity="0.12" />
</svg>"""
    return svg
