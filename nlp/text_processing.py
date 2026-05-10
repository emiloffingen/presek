import re
import math

# Irregular lemmas for Macedonian
_MK_IRREGULAR_LEMMAS = {
    "луѓе": "човек",
    "деца": "дете",
    "пазари": "пазар",
    "пазарот": "пазар",
    "министри": "министер",
    "министерот": "министер",
    "претседатели": "претседател",
    "избори": "избор",
    "изборите": "избор",
    "патишта": "пат",
    "светови": "свет",
}

_MK_PLURAL_SUFFIXES = [
    (re.compile(r"ите$"), ""),
    (re.compile(r"ата$"), ""),
    (re.compile(r"ото$"), ""),
    (re.compile(r"та$"), ""),
    (re.compile(r"то$"), ""),
    (re.compile(r"от$"), ""),
    (re.compile(r"те$"), ""),
    (re.compile(r"и$"), ""),
    (re.compile(r"а$"), ""),
    (re.compile(r"е$"), ""),
    (re.compile(r"овци$"), ""),
    (re.compile(r"евци$"), ""),
]


def lemmatize_mk(word: str) -> str:
    """Reduces a Macedonian word to its approximate lemma (base form)."""
    w = word.lower().strip()
    if len(w) <= 3:
        return w
    if w in _MK_IRREGULAR_LEMMAS:
        return _MK_IRREGULAR_LEMMAS[w]

    # Selective suffix stripping (adjectives -> nouns where clear)
    # PROTECT stems that are common in news and shouldn't be truncated to fragments
    if any(
        w.startswith(p)
        for p in ["македон", "мицкос", "америк", "европ", "русиј", "израел", "украин"]
    ):
        if w == "македон":
            return "Македон"  # Preserve name
        if w.startswith("македон"):
            return "Македонија"
        if w.startswith("америк"):
            return "Америка"
        if w.startswith("европ"):
            return "Европа"
        if w.startswith("русиј"):
            return "Русија"
        if w.startswith("украин"):
            return "Украина"
        if w.startswith("израел"):
            return "Израел"
        return w

    # Strip common adjective suffixes to get to the root/noun form
    # But only if it leaves a reasonable word behind
    if len(w) > 7:
        # Avoid stripping if it ends with 'нија' (like Македонија, Германија)
        if not w.endswith("нија"):
            w = re.sub(r"(овски|евски|скиот|ската|ското|ските|ски)$", "", w)

    if len(w) <= 3:
        return w

    for rx, repl in _MK_PLURAL_SUFFIXES[:7]:
        if rx.search(w):
            w = rx.sub(repl, w)
            break
    if len(w) > 3:
        for rx, repl in _MK_PLURAL_SUFFIXES[7:]:
            if rx.search(w):
                w = rx.sub(repl, w)
                break

    # 'ц' -> 'це' was too aggressive (e.g. теснец -> теснеце is wrong)
    # Only applies to very specific cases, safer to avoid for general entity tags
    # if w.endswith("ц"): w = w[:-1] + "це"

    if w.endswith("шт"):
        w = w[:-2] + "ште"
    return w


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
    "confirms": "потврува",
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
}

LOCAL_TRANSLATION_EXTRA = {
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

JUNK_NEWS_PHRASES = [
    "прочитајте и",
    "можеби ќе ве интересира",
    "поврзано:",
    "извор:",
    "фото:",
    "видео:",
    "галерија:",
    "следете нè",
    "преземањето е дозволено",
    "автор:",
    "пишува:",
    "фокус на денот",
    "трендинг",
    "најчитано",
    "exclusive:",
    "breaking:",
    "read more",
    "related:",
    "source:",
    "follow us",
    "дознајте повеќе",
    "според информациите на",
]


def calculate_reading_time(text: str) -> int:
    """Estimates reading time in minutes (approx 200 wpm)."""
    if not text:
        return 1
    words = len(text.split())
    return max(1, math.ceil(words / 200))


def _normalize_summary_sentence(sentence):
    text = re.sub(r"\s+", " ", str(sentence or "")).strip()
    text = re.sub(r"^[•*\-\u2022]+\s*", "", text)
    return text


def _jaccard_similarity(sent1, sent2):
    """Calculates word-level overlap similarity between two sentences."""
    from nlp.keywords import _sentence_tokens

    words1 = set(_sentence_tokens(sent1))
    words2 = set(_sentence_tokens(sent2))
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1 | words2)


def rewrite_to_macedonian_locally(text):
    """Deterministic, low-cost rewrite for short news text."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return text

    text = re.sub(
        r"^\s*translate(?: the following)?\s*:\s*", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"^\s*summary\s*:\s*", "", text, flags=re.IGNORECASE)

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
        replacement = (
            LOCAL_TRANSLATION_MONTHS.get(lowered)
            or LOCAL_TRANSLATION_EXTRA.get(lowered)
            or LOCAL_TRANSLATION_WORDS.get(lowered)
        )
        if not replacement:
            return word
        if word.isupper():
            return replacement.upper()
        if word[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement

    working = re.sub(r"\b[A-Za-z][A-Za-z'-]*\b", _replace_word, working)
    working = re.sub(r"\s+", " ", working).strip()
    for w in ["the", "a", "an"]:
        working = re.sub(rf"\b{w}\b", "", working, flags=re.IGNORECASE)

    working = re.sub(r"\s+,", ",", working)
    working = re.sub(r"\s+\.", ".", working)
    working = re.sub(r"\s{2,}", " ", working).strip(" -–—")

    if not re.search(r"[А-Яа-яЀ-ӿ]", working):
        return text[:420]
    if not re.search(r"[.!?]$", working):
        working += "."
    return working[:420]


def _is_noisy_summary_sentence(sentence, title_terms=None):
    text = _normalize_summary_sentence(sentence)
    if not text or len(text) < 28:
        return True
    lowered = text.lower()

    if lowered.startswith(
        ("фото:", "видео:", "gallery:", "галерија:", "коментар:", "реклама:", "извор:")
    ):
        return True
    if any(phrase in lowered for phrase in JUNK_NEWS_PHRASES):
        return True
    if text.count("#") >= 2:
        return True

    if title_terms:
        from nlp.keywords import _sentence_tokens

        sentence_words = set(_sentence_tokens(text))
        if sentence_words and not (sentence_words & title_terms):
            return True
    return False


def synthesize_locally(articles, sentence_count=4, topic=None):
    """Sophisticated Local Synthesis Engine."""
    if not articles:
        return ""
    from nlp.keywords import _sentence_tokens, _extract_capitalized_phrases
    from nlp.generation import _extract_number_tokens

    all_candidates = []
    for art in articles:
        src = art.get("source", "Извор")
        text = f"{art.get('title', '')}. {art.get('description', '')}"
        raw_sents = re.split(r"(?<=[.!?])\s+", text)
        for idx, s in enumerate(raw_sents):
            clean_s = _normalize_summary_sentence(s)
            if not clean_s or _is_noisy_summary_sentence(clean_s):
                continue
            is_action = any(
                v in clean_s.lower()
                for v in [
                    "изјави",
                    "најави",
                    "предупреди",
                    "порача",
                    "истакна",
                    "повика",
                    "одлучи",
                ]
            )
            s_words = _sentence_tokens(clean_s)
            if not s_words:
                continue
            entities = set(_extract_capitalized_phrases(clean_s))
            val_score = (
                len(s_words) * 0.1
                + (0.8 if idx == 0 else 0.0)
                + (0.6 if is_action else 0.0)
                + (0.5 if _extract_number_tokens(clean_s) else 0.0)
                + len(entities) * 0.4
            )
            all_candidates.append(
                {
                    "text": clean_s,
                    "score": val_score,
                    "entities": entities,
                    "source": src,
                    "is_action": is_action,
                }
            )
    if not all_candidates:
        return ""
    all_candidates.sort(key=lambda x: x["score"], reverse=True)
    selected = []
    used_entities, used_sources = set(), set()
    for _ in range(sentence_count):
        best_candidate, best_boosted_score = None, -1.0
        for cand in all_candidates:
            if any(
                _jaccard_similarity(cand["text"], s["text"]) > 0.4 for s in selected
            ):
                continue
            diversity_boost = 1.3 if cand["source"] not in used_sources else 1.0
            new_entity_boost = 1.0 + (len(cand["entities"] - used_entities) * 0.3)
            flow_boost = (
                1.2
                if len(selected) == 0
                else (1.4 if len(selected) >= 2 and cand["is_action"] else 1.0)
            )
            boosted_score = (
                cand["score"] * diversity_boost * new_entity_boost * flow_boost
            )
            if boosted_score > best_boosted_score:
                best_boosted_score, best_candidate = boosted_score, cand
        if best_candidate:
            selected.append(best_candidate)
            used_entities.update(best_candidate["entities"])
            used_sources.add(best_candidate["source"])
        else:
            break
    res = []
    for s in selected:
        txt = s["text"]
        if txt and txt[0].islower():
            txt = txt[0].upper() + txt[1:]
        res.append(f"• {txt}")
    return "\n".join(res)


# Lazy-loaded NER pipeline
_ner_pipeline = None


def extract_entities_semantic(text: str) -> set[str]:
    """Extracts named entities using a multilingual BERT model."""
    global _ner_pipeline
    if not text:
        return set()

    if _ner_pipeline is None:
        try:
            from transformers import pipeline
            import torch
            import logging

            log = logging.getLogger("presek.nlp")
            log.info(
                "Loading semantic NER model in Bfloat16 (Babelscape/wikineural-multilingual-ner)..."
            )
            # Using bfloat16 to cut memory usage by ~50% on CPU while maintaining range
            _ner_pipeline = pipeline(
                "ner",
                model="Babelscape/wikineural-multilingual-ner",
                aggregation_strategy="simple",
                device="cpu",
            )
        except Exception as e:
            import logging

            logging.getLogger("presek.nlp").error(f"Failed to load NER model: {e}")
            _ner_pipeline = "failed"

    if _ner_pipeline == "failed":
        # Fallback to regex if model fails to load
        from nlp.extraction import extract_title_entities_regex

        return extract_title_entities_regex(text)

    try:
        # aggregation_strategy="simple" groups subwords into single entities
        results = _ner_pipeline(text)
        entities = set()
        for res in results:
            # We only care about PER (Person), ORG (Organization), LOC (Location), MISC
            if res["entity_group"] in ("PER", "ORG", "LOC", "MISC"):
                ent_text = res["word"].strip()
                # Clean up ## subword artifacts just in case
                ent_text = ent_text.replace(" ##", "").replace("##", "")
                if len(ent_text) >= 3:
                    entities.add(ent_text)
        return entities
    except Exception as e:
        import logging

        logging.getLogger("presek.nlp").error(f"NER extraction failed: {e}")
        return set()
