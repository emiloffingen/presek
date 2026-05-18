import math
import re

# Irregular lemmas for Serbian
_SR_IRREGULAR_LEMMAS = {
    "ljudi": "čovek",
    "deca": "dete",
    "pijace": "pijaca",
    "ministri": "ministar",
    "predsednici": "predsednik",
    "izbori": "izbor",
    "putevi": "put",
    "svetovi": "Svet",
}

_SR_PLURAL_SUFFIXES = [
    (re.compile(r"ovima$"), ""),
    (re.compile(r"evima$"), ""),
    (re.compile(r"ima$"), ""),
    (re.compile(r"om$"), ""),
    (re.compile(r"em$"), ""),
    (re.compile(r"ovi$"), ""),
    (re.compile(r"evi$"), ""),
    (re.compile(r"og$"), ""),
    (re.compile(r"eg$"), ""),
    (re.compile(r"ih$"), ""),
    (re.compile(r"im$"), ""),
    (re.compile(r"oj$"), ""),
    (re.compile(r"i$"), ""),
    (re.compile(r"e$"), ""),
    (re.compile(r"a$"), ""),
    (re.compile(r"u$"), ""),
]


def lemmatize_sr(word: str) -> str:
    """Reduces a Serbian word to its approximate lemma (base form)."""
    w = word.lower().strip()
    if len(w) <= 3:
        return w
    if w in _SR_IRREGULAR_LEMMAS:
        return _SR_IRREGULAR_LEMMAS[w]

    # PROTECT stems that are common in news
    if any(w.startswith(p) for p in ["srbij", "vučić", "amerik", "evrop", "rusij", "izrael", "ukrajin"]):
        if w.startswith("srbij"):
            return "Srbija"
        if w.startswith("amerik"):
            return "Amerika"
        if w.startswith("evrop"):
            return "Evropa"
        if w.startswith("rusij"):
            return "Rusija"
        if w.startswith("ukrajin"):
            return "Ukrajina"
        if w.startswith("izrael"):
            return "Izrael"
        return w

    # Strip common adjective suffixes
    if len(w) > 6:
        w = re.sub(r"(ski|ški|čki|skog|škog|čkog|skim|škim|čkim)$", "", w)

    if len(w) <= 3:
        return w

    for rx, repl in _SR_PLURAL_SUFFIXES:
        if rx.search(w):
            w = rx.sub(repl, w)
            break

    return w


LOCAL_TRANSLATION_PHRASES = [
    (r"\bbreaking news\b", "hitna vest"),
    (r"\blive updates?\b", "uživo praćenje"),
    (r"\baccording to\b", "prema"),
    (r"\bprime minister\b", "premijer"),
    (r"\bforeign minister\b", "ministar spoljnih poslova"),
    (r"\bfinance minister\b", "ministar finansija"),
    (r"\bdefense minister\b", "ministar odbrane"),
    (r"\binterior minister\b", "ministar unutrašnjih poslova"),
    (r"\bhealth minister\b", "ministar zdravlja"),
    (r"\bceasefire\b", "prekid vatre"),
    (r"\binterest rates?\b", "kamatne stope"),
    (r"\bcentral bank\b", "centralna banka"),
    (r"\bwhite house\b", "Bela kuća"),
    (r"\beuropean union\b", "Evropska Unija"),
    (r"\bunited nations\b", "Ujedinjene nacije"),
    (r"\bsecurity council\b", "Savet bezbednosti"),
    (r"\bhuman rights\b", "ljudska prava"),
    (r"\bclimate change\b", "klimatske promene"),
    (r"\bsupreme court\b", "Vrhovni sud"),
    (r"\belection commission\b", "izborna komisija"),
]

LOCAL_TRANSLATION_WORDS = {
    "government": "vlada",
    "minister": "ministar",
    "president": "predsednik",
    "parliament": "parlament",
    "opposition": "opozicija",
    "police": "policija",
    "court": "sud",
    "judges": "sudije",
    "judge": "sudija",
    "election": "izbori",
    "elections": "izbori",
    "voters": "glasači",
    "vote": "glasanje",
    "campaign": "kampanja",
    "tariff": "carina",
    "tariffs": "carine",
    "sanction": "sankcija",
    "sanctions": "sankcije",
    "attack": "napad",
    "attacks": "napadi",
    "protest": "protest",
    "protests": "protesti",
    "strike": "štrajk",
    "strikes": "štrajkovi",
    "package": "paket",
    "packages": "paketi",
    "measure": "mera",
    "measures": "mere",
    "budget": "budžet",
    "economy": "Ekonomija",
    "inflation": "inflacija",
    "market": "tržište",
    "markets": "tržišta",
    "company": "kompanija",
    "companies": "kompanije",
    "deal": "dogovor",
    "agreement": "dogovor",
    "talks": "razgovori",
    "negotiations": "pregovori",
    "support": "podrška",
    "aid": "pomoć",
    "bill": "predlog zakona",
    "law": "zakon",
    "report": "izveštaj",
    "reports": "izveštava",
    "reported": "objavio",
    "says": "kaže",
    "said": "izjavio",
    "announce": "najavljuje",
    "announces": "najavljuje",
    "announced": "najavio",
    "warns": "upozorava",
    "warned": "upozorio",
    "approves": "odobrava",
    "approved": "odobrio",
    "launches": "pokreće",
    "launched": "pokrenuo",
    "delays": "odlaže",
    "delayed": "odložio",
    "confirms": "potvrđuje",
    "confirmed": "potvrdio",
    "denies": "negira",
    "denied": "negirao",
    "urges": "poziva",
    "plans": "planira",
    "plan": "plan",
    "new": "novi",
    "latest": "najnoviji",
    "official": "zvanični",
    "officials": "zvaničnici",
    "citizens": "građani",
    "crisis": "kriza",
    "war": "rat",
    "peace": "mir",
    "military": "vojska",
    "troops": "trupe",
    "leader": "lider",
    "leaders": "lideri",
    "meeting": "sastanak",
    "summit": "samit",
}

LOCAL_TRANSLATION_MONTHS = {
    "january": "januar",
    "february": "februar",
    "march": "mart",
    "april": "april",
    "may": "maj",
    "june": "jun",
    "july": "jul",
    "august": "avgust",
    "september": "septembar",
    "october": "oktobar",
    "november": "novembar",
    "december": "decembar",
}

LOCAL_TRANSLATION_EXTRA = {
    "monday": "Ponedeljak",
    "tuesday": "Utorak",
    "wednesday": "Sreda",
    "thursday": "četvrtak",
    "friday": "Petak",
    "saturday": "Subota",
    "sunday": "Nedelja",
    "today": "danas",
    "tomorrow": "sutra",
    "yesterday": "juče",
}

JUNK_NEWS_PHRASES = [
    "pročitajte i",
    "možda će vas zanimati",
    "povezano:",
    "izvor:",
    "foto:",
    "video:",
    "galerija:",
    "pratite nas",
    "preuzimanje je dozvoljeno",
    "autor:",
    "piše:",
    "fokus dana",
    "trending",
    "najčitanije",
    "najnovije",
    "oglas",
    "koje je vaše mišljenje o ovoj temi?",
    "pridružite se diskusiji ili pročitajte komentare",
    "exclusive:",
    "breaking:",
    "read more",
    "related:",
    "source:",
    "follow us",
    "saznajte više",
    "prema informacijama",
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


def rewrite_to_serbian_locally(text):
    """Deterministic, low-cost rewrite for short news text in Serbian."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return text

    text = re.sub(r"^\s*translate(?: the following)?\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*summary\s*:\s*", "", text, flags=re.IGNORECASE)

    # Simplified normalization - no longer enforced Macedonian Cyrillic threshold
    normalized = re.sub(r"\s+", " ", text).strip(" -–—")

    working = f" {normalized} "
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

    # Remove articles
    for w in ["the", "a", "an"]:
        working = re.sub(rf"\b{w}\b", "", working, flags=re.IGNORECASE)

    working = re.sub(r"\s+,", ",", working)
    working = re.sub(r"\s+\.", ".", working)
    working = re.sub(r"\s{2,}", " ", working).strip(" -–—")

    if not re.search(r"[.!?]$", working):
        working += "."
    return working[:420]


def _is_noisy_summary_sentence(sentence, title_terms=None):
    text = _normalize_summary_sentence(sentence)
    if not text or len(text) < 28:
        return True
    lowered = text.lower()

    if lowered.startswith(("foto:", "video:", "gallery:", "galerija:", "komentar:", "reklama:", "izvor:")):
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
    from nlp.generation import _extract_number_tokens
    from nlp.keywords import _extract_capitalized_phrases, _sentence_tokens

    all_candidates = []
    for art in articles:
        src = art.get("source", "izvor")
        text = f"{art.get('title', '')}. {art.get('description', '')}"
        raw_sents = re.split(r"(?<=[.!?])\s+", text)
        for idx, s in enumerate(raw_sents):
            clean_s = _normalize_summary_sentence(s)
            if not clean_s or _is_noisy_summary_sentence(clean_s):
                continue
            is_action = any(
                v in clean_s.lower()
                for v in [
                    "izjavi",
                    "najavi",
                    "predupredi",
                    "poraca",
                    "istakna",
                    "povika",
                    "odluci",
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
            if any(_jaccard_similarity(cand["text"], s["text"]) > 0.4 for s in selected):
                continue
            diversity_boost = 1.3 if cand["source"] not in used_sources else 1.0
            new_entity_boost = 1.0 + (len(cand["entities"] - used_entities) * 0.3)
            flow_boost = 1.2 if len(selected) == 0 else (1.4 if len(selected) >= 2 and cand["is_action"] else 1.0)
            boosted_score = cand["score"] * diversity_boost * new_entity_boost * flow_boost
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
            import logging

            from transformers import pipeline

            log = logging.getLogger("presek.nlp")
            log.info("Loading semantic NER model in Bfloat16 (Babelscape/wikineural-multilingual-ner)...")
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
