"""
entities.py — Hybrid entity extraction for Presek.

Pipeline:
1. Exact-match against the curated KNOWN_ENTITIES lexicon (highest precision)
2. spaCy multilingual NER (`xx_ent_wiki_sm`) when available — catches novel
   people / orgs / locations the lexicon doesn't know about
3. Regex capitalized-phrase heuristic as a final fallback
"""

import logging
import os
import re
import threading

log = logging.getLogger("presek")

_spacy_nlp = None
_spacy_lock = threading.Lock()
_spacy_unavailable = False


def _get_spacy():
    """Lazy-load spaCy multilingual NER once per process. Returns None if
    spaCy or the model is unavailable — callers must handle the fallback."""
    global _spacy_nlp, _spacy_unavailable
    if os.environ.get("PRESEK_DISABLE_SPACY", "").lower() in {"1", "true", "yes"}:
        return None
    if _spacy_unavailable:
        return None
    if _spacy_nlp is not None:
        return _spacy_nlp
    with _spacy_lock:
        if _spacy_nlp is not None:
            return _spacy_nlp
        try:
            import spacy
        except ImportError:
            log.info("[entities] spaCy not installed — using regex fallback only")
            _spacy_unavailable = True
            return None
        try:
            _spacy_nlp = spacy.load("xx_ent_wiki_sm", disable=["tagger", "parser", "lemmatizer"])
            log.info("[entities] spaCy xx_ent_wiki_sm NER loaded")
        except Exception as e:
            log.warning(
                "[entities] spaCy model 'xx_ent_wiki_sm' not available (%s). "
                "Install with: python -m spacy download xx_ent_wiki_sm",
                e,
            )
            _spacy_unavailable = True
            return None
        return _spacy_nlp


# spaCy label → internal type mapping
_SPACY_LABEL_MAP = {
    "PER": "PERSON",
    "PERSON": "PERSON",
    "ORG": "ORG",
    "LOC": "LOC",
    "GPE": "LOC",
    "MISC": "ENTITY",
}

# Common Macedonian entities (VIPs) for exact matching
KNOWN_ENTITIES = {
    # Politics - People
    "Ali Ahmeti": "PERSON",
    "Antonio Milososki": "PERSON",
    "Arben Taravari": "PERSON",
    "Artan Grubi": "PERSON",
    "Afrim Gasi": "PERSON",
    "Bilal Kasami": "PERSON",
    "Bojan Maricic": "PERSON",
    "Branko Crvenkovski": "PERSON",
    "Bujar Osmani": "PERSON",
    "Venko Filipce": "PERSON",
    "Vlado Misajlovski": "PERSON",
    "Gordana Siljanovska-Davkova": "PERSON",
    "Dane Taleski": "PERSON",
    "Dimitar Apasiev": "PERSON",
    "Dimitar Dimovski": "PERSON",
    "Dimitar Kovacevski": "PERSON",
    "Dragan Kovacki": "PERSON",
    "Zijadin Sela": "PERSON",
    "Zoran Zaev": "PERSON",
    "Izet Medziti": "PERSON",
    "Igor Janusev": "PERSON",
    "Jovan Mitreski": "PERSON",
    "Katerina Canevska": "PERSON",
    "Kresnik Bektesi": "PERSON",
    "Ljupco Nikolovski": "PERSON",
    "Maksim Dimitrievski": "PERSON",
    "Mile Lefkov": "PERSON",
    "Nikola Gruevski": "PERSON",
    "Oliver Spasovski": "PERSON",
    "Petar Bogojeski": "PERSON",
    "Saso Mijalkov": "PERSON",
    "Slavjanka Petrovska": "PERSON",
    "Stevo Pendarovski": "PERSON",
    "Timco Mucunski": "PERSON",
    "Fatmir Bitici": "PERSON",
    "Halil Snopce": "PERSON",
    "Hristijan Mickoski": "PERSON",
    # Global - People
    "Donald Tramp": "PERSON",
    "Dzo Bajden": "PERSON",
    "Vladimir Putin": "PERSON",
    "Volodimir Zelenski": "PERSON",
    "Emanuel Makron": "PERSON",
    "Olaf Solc": "PERSON",
    "Viktor Orban": "PERSON",
    "Aleksandar Vucic": "PERSON",
    "Kirijakos Micotakis": "PERSON",
    "Redzep Taip Erdogan": "PERSON",
    "Si Dzinping": "PERSON",
    "Risi Sunak": "PERSON",
    "Kir Starmer": "PERSON",
    "Kamala Haris": "PERSON",
    "Ilon Mask": "PERSON",
    "Papata Francisk": "PERSON",
    "Benjamin Netanjahu": "PERSON",
    "Robert Fico": "PERSON",
    "Entoni Blinken": "PERSON",
    "Kim Dzong Un": "PERSON",
    "Majk Pens": "PERSON",
    "Dzej Di Vens": "PERSON",
    "Robert Kenedi Pomladiot": "PERSON",
    "Vivek Ramasvami": "PERSON",
    "Rumen Radev": "PERSON",
    "Bojko Borisov": "PERSON",
    "Mark Rute": "PERSON",
    "Pedro Sancez": "PERSON",
    "Antonio Guteres": "PERSON",
    "Ursula fon der Lajen": "PERSON",
    "Zozep Borel": "PERSON",
    "Mark Zakerberg": "PERSON",
    "Bil Gejts": "PERSON",
    "Dzef Bezos": "PERSON",
    "Dzordz Soros": "PERSON",
    # Organizations - Domestic
    "Vlada": "ORG",
    "Sobranie": "ORG",
    "VMRO-DPMNE": "ORG",
    "SDSM": "ORG",
    "DUI": "ORG",
    "Alijansa za Albancite": "ORG",
    "Levica": "ORG",
    "ZNAM": "ORG",
    "Vredi": "ORG",
    "Alternativa": "ORG",
    "Dvizenje Besa": "ORG",
    "Demokratsko dvizenje": "ORG",
    "GROM": "ORG",
    "LDP": "ORG",
    "MVR": "ORG",
    "Ministerstvo za vnatresni raboti": "ORG",
    "Ministerstvo za Zdravstvo": "ORG",
    "Ministerstvo za Obrazovanje": "ORG",
    "Ministerstvo za odbrana": "ORG",
    "Ministerstvo za nadvoresni raboti": "ORG",
    "MNR": "ORG",
    "Ministerstvo za transport i vrski": "ORG",
    "Ministerstvo za Ekonomija": "ORG",
    "Ministerstvo za finansii": "ORG",
    "Ministerstvo za pravda": "ORG",
    "Ministerstvo za zemjodelstvo": "ORG",
    "Ministerstvo za Kultura": "ORG",
    "UJP": "ORG",
    "Carinska uprava": "ORG",
    "Agencija za mladi i Sport": "ORG",
    "Grad Beograd": "ORG",
    "JSP": "ORG",
    "Vodovod i kanalizacija": "ORG",
    "Parkovi i zelenilo": "ORG",
    "Komunalna higiena": "ORG",
    "Sudski sovet": "ORG",
    "Ustaven sud": "ORG",
    "Apelacionen sud": "ORG",
    "Krivicen sud": "ORG",
    "Osnoven sud": "ORG",
    "Vrhoven sud": "ORG",
    "Drzavna izborna komisija": "ORG",
    "DIK": "ORG",
    "Drzaven zavod za statistika": "ORG",
    "DZS": "ORG",
    "Agencija za hrana i veterinarstvo": "ORG",
    "ESM": "ORG",
    "MEPSO": "ORG",
    "EVN": "ORG",
    "AD Elektrani": "ORG",
    "Agencija za audio i audiovizuelni mediumski uslugi": "ORG",
    "AVMU": "ORG",
    # Organizations - International
    "Evropska Unija": "ORG",
    "EU": "ORG",
    "NATO": "ORG",
    "ON": "ORG",
    "Obedineti Nacii": "ORG",
    "Svetska zdravstvena organizacija": "ORG",
    "SZO": "ORG",
    "MMF": "ORG",
    "Svetska banka": "ORG",
    "Evropska komisija": "ORG",
    "Evropski parlament": "ORG",
    "Evropska centralna banka": "ORG",
    "ECB": "ORG",
    "Sovet na Evropa": "ORG",
    "KFOR": "ORG",
    "FED": "ORG",
    "OBSE": "ORG",
    "Haski tribunal": "ORG",
    "UNICEF": "ORG",
    "UNESKO": "ORG",
    "Amnesti internesnal": "ORG",
    "Crven krst": "ORG",
    "Stejt department": "ORG",
    "Kremlj": "ORG",
    "Belata kuca": "ORG",
    "Pentagon": "ORG",
    "CIA": "ORG",
    "FBI": "ORG",
    "HAMAS": "ORG",
    "OPEK": "ORG",
    "Ormuz": "LOC",
}

# Words to ignore (common words that are capitalized at start of sentence or follow entities)
IGNORE_WORDS = {
    "danas",
    "sutra",
    "juce",
    "Povece",
    "Spored",
    "Kako",
    "ova",
    "ova",
    "Toa",
    "Site",
    "Nema",
    "Ima",
    "Bese",
    "Bide",
    "Ovie",
    "Nikoj",
    "Sekoj",
    "Vesta",
    "Informacija",
    "Mediumite",
    "Novite",
    "Povtorno",
    "Namesto",
    "Dodeka",
    "Poradi",
    "Zaradi",
    "Iako",
    "Osven",
    "Medjutoa",
    "Sepak",
    "Zatoa",
    "No",
    "Znaci",
    "Koga",
    "Samo",
    "Ona",
    "Isto",
    "Istoto",
    "Tokmu",
    "Togas",
    "Sprotivno",
    "Vprocem",
    "Medju",
    "Preku",
    "Vo",
    "Na",
    "Za",
    "Od",
    "So",
    "Do",
    "Ne",
    "Da",
    "Dali",
    "Prvo",
    "Prviot",
    "Dva",
    "Tri",
    "Potoa",
    "Posle",
    "Fon",
    "Der",
    "Von",
    "Vece",
    "Koj",
    "Koja",
    "Koi",
    "Sto",
    "Kade",
    "Zosto",
    "Kakov",
    "Kakva",
    "Kakvi",
    "Negov",
    "Negova",
    "Nivni",
    "Moze",
    "Mozebi",
    "Eden",
    "Edna",
    "Edno",
    "Pred",
    "Pod",
    "Nad",
    "Medju",
    "Pomedju",
}

# Regex for detecting Macedonian proper nouns (starts with capital letter)
# Uses a negative lookahead to avoid matching common trailing noise words
_trailing_ignore = "|".join(IGNORE_WORDS)
PROPER_NOUN_PATTERN = re.compile(
    r"(?:\b[A-Za-z\u0400-\u04FF][A-Za-z0-9\u0400-\u04FF]+\b(?:[\s-]+\b(?!" + _trailing_ignore + r")[A-Za-z\u0400-\u04FF][A-Za-z0-9\u0400-\u04FF]+\b){0,3})"
)


# Normalize variants to canonical forms
ENTITY_ALIASES = {
    "Mickoski": "Hristijan Mickoski",
    "Kovacevski": "Dimitar Kovacevski",
    "Pendarovski": "Stevo Pendarovski",
    "Siljanovska": "Gordana Siljanovska-Davkova",
    "Siljanovska-Davkova": "Gordana Siljanovska-Davkova",
    "Tramp": "Donald Tramp",
    "Putin": "Vladimir Putin",
    "Vucic": "Aleksandar Vucic",
    "Zelenski": "Volodimir Zelenski",
    "Apasiev": "Dimitar Apasiev",
    "Makron": "Emanuel Makron",
    "Kurti": "Albin Kurti",
    "Filipce": "Venko Filipce",
    "Gruevski": "Nikola Gruevski",
    "Janevska": "Vesna Janevska",
    "Osmani": "Bujar Osmani",
    "Osmanoska": "Bujar Osmani",
    "VMRO": "VMRO-DPMNE",
    "VMRO DPMNE": "VMRO-DPMNE",
    "Micko": "Hristijan Mickoski",
    "Hristijan Micko": "Hristijan Mickoski",
    "Ormuskiot": "Ormuz",
    "Ormutskiot": "Ormuz",
    "ON": "Obedineti Nacii",
    "SZO": "Svetska zdravstvena organizacija",
    "MVR": "Ministerstvo za vnatresni raboti",
    "MNR": "Ministerstvo za nadvoresni raboti",
    "Gru": "Nikola Gruevski",
    "Ursula fon der": "Ursula fon der Lajen",
    "Ursula Fon Der": "Ursula fon der Lajen",
    "fon der Lajen": "Ursula fon der Lajen",
    "Fon der Lajen": "Ursula fon der Lajen",
    "Lajen": "Ursula fon der Lajen",
    "Evropskata komisija": "Evropska komisija",
    "EK": "Evropska komisija",
    # Common Latin-script renderings from international wires
    "Donald Trump": "Donald Tramp",
    "Joe Biden": "Dzo Bajden",
    "Vladimir Putin": "Vladimir Putin",
    "Volodymyr Zelenskyy": "Volodimir Zelenski",
    "Volodymyr Zelensky": "Volodimir Zelenski",
    "Emmanuel Macron": "Emanuel Makron",
    "Olaf Scholz": "Olaf Solc",
    "Viktor Orban": "Viktor Orban",
    "Aleksandar Vucic": "Aleksandar Vucic",
    "Kyriakos Mitsotakis": "Kirijakos Micotakis",
    "Recep Tayyip Erdogan": "Redzep Taip Erdogan",
    "Xi Jinping": "Si Dzinping",
    "Rishi Sunak": "Risi Sunak",
    "Keir Starmer": "Kir Starmer",
    "Kamala Harris": "Kamala Haris",
    "Elon Musk": "Ilon Mask",
    "Pope Francis": "Papata Francisk",
    "Benjamin Netanyahu": "Benjamin Netanjahu",
    "Robert Fico": "Robert Fico",
    "Antony Blinken": "Entoni Blinken",
    "Kim Jong Un": "Kim Dzong Un",
    "Mark Zuckerberg": "Mark Zakerberg",
    "Bill Gates": "Bil Gejts",
    "Jeff Bezos": "Dzef Bezos",
    "George Soros": "Dzordz Soros",
}

_unique_person_surnames = {}
_surname_to_person = {}
for _name, _etype in KNOWN_ENTITIES.items():
    if _etype != "PERSON":
        continue
    _parts = [part for part in re.split(r"[\s-]+", _name) if part]
    if len(_parts) < 2:
        continue
    # Consider all parts except first name as potential surnames for mix-up detection
    for _part in _parts[1:]:
        if len(_part) >= 4:
            _surname_to_person.setdefault(_part, set()).add(_name)

for _surname, _people in _surname_to_person.items():
    if len(_people) == 1 and _surname not in ENTITY_ALIASES:
        _unique_person_surnames[_surname] = next(iter(_people))

ENTITY_ALIASES.update(_unique_person_surnames)

_ENTITY_ALIASES_CASEFOLDED = {str(alias).strip().casefold(): canonical for alias, canonical in ENTITY_ALIASES.items()}
_KNOWN_ENTITIES_ORDERED = sorted(KNOWN_ENTITIES.items(), key=lambda item: (-len(item[0]), item[0]))
_ENTITY_ALIASES_ORDERED = sorted(ENTITY_ALIASES.items(), key=lambda item: (-len(item[0]), item[0]))

_KNOWN_SURNAMES = {}
_KNOWN_FIRSTNAMES = {}
for _name, _etype in KNOWN_ENTITIES.items():
    if _etype == "PERSON":
        _parts = [part for part in re.split(r"[\s-]+", _name) if part]
        if len(_parts) >= 2:
            _KNOWN_FIRSTNAMES[_parts[0]] = _name
            # All parts except the first are considered surnames for the fix logic
            for _part in _parts[1:]:
                if len(_part) >= 4:
                    _KNOWN_SURNAMES[_part] = _name
            # Also add the full multi-part surname if it has a hyphen
            if "-" in _name:
                _surname_part = _name.split(None, 1)[-1]
                if len(_surname_part) >= 4:
                    _KNOWN_SURNAMES[_surname_part] = _name

# Include common single-word aliases as potential surnames for the fix logic
for _alias, _canonical in ENTITY_ALIASES.items():
    if " " not in _alias and len(_alias) >= 4 and _canonical in KNOWN_ENTITIES:
        if KNOWN_ENTITIES[_canonical] == "PERSON":
            _KNOWN_SURNAMES[_alias] = _canonical

_NAME_SURFACE_RE = re.compile(r"^[A-Za-z\u0400-\u04FF' .-]+$")


def _title_case_name_part(part: str) -> str:
    def _fix_piece(piece: str) -> str:
        if not piece:
            return ""
        return piece[:1].upper() + piece[1:].lower()

    hyphenated = ["'".join(_fix_piece(piece) for piece in apostrophe.split("'")) for apostrophe in part.split("-")]
    return "-".join(hyphenated)


def normalize_person_surface_name(name: str) -> str:
    """
    Normalize human-readable person names without disturbing generic tags.

    Handles:
    - exact alias/canonical matches via the curated entity tables
    - all-lowercase / all-uppercase names -> title case
    - known two-part surname-first forms -> canonical first-name-first form
    """
    clean = re.sub(r"\s+", " ", str(name or "")).strip(" -–—,.;:!?()[]{}\"'")
    if not clean:
        return ""

    canonical = _ENTITY_ALIASES_CASEFOLDED.get(clean.casefold())
    if canonical and KNOWN_ENTITIES.get(canonical) == "PERSON":
        return canonical

    if not _NAME_SURFACE_RE.fullmatch(clean):
        return clean

    parts = [part for part in clean.split(" ") if part]
    if not parts:
        return ""

    formatted_parts = [_title_case_name_part(part) for part in parts]
    formatted = " ".join(formatted_parts)

    if KNOWN_ENTITIES.get(formatted) == "PERSON":
        return formatted

    canonical = _ENTITY_ALIASES_CASEFOLDED.get(formatted.casefold())
    if canonical and KNOWN_ENTITIES.get(canonical) == "PERSON":
        return canonical

    if len(formatted_parts) == 2:
        first_part, second_part = formatted_parts
        reversed_candidate = f"{second_part} {first_part}"
        if (
            first_part in _KNOWN_SURNAMES
            and second_part in _KNOWN_FIRSTNAMES
            and KNOWN_ENTITIES.get(reversed_candidate) == "PERSON"
        ):
            return reversed_candidate

    if clean == clean.lower() or clean == clean.upper():
        return formatted

    return clean


def validate_person_names(text: str | list[str]) -> str | list[str]:
    """
    Heuristic to fix AI hallucinations of famous names.
    If it finds 'Dimitar Filipce' but 'Filipce' is known as 'Venko', and 'Dimitar' is known as 'Kovacevski',
    it checks for likely mixups and restores canonical forms.
    """
    if not text:
        return text

    is_list = isinstance(text, list)
    if is_list:
        joined_text = "\n".join(str(t) for t in text)
    else:
        joined_text = str(text)

    # 1. Look for known name phrases (2 or 3 parts)
    all_words = re.findall(r"\b[A-Za-z\u0400-\u04FF][A-Za-z\u0400-\u04FF-]+(?:\s+[A-Za-z\u0400-\u04FF][A-Za-z\u0400-\u04FF-]+){1,2}\b", joined_text)
    all_words = list(set(all_words))  # De-duplicate for efficiency
    all_words.sort(key=len, reverse=True)

    for pair in all_words:
        if pair in KNOWN_ENTITIES:
            continue

        # Normalize whitespace
        clean_pair = re.sub(r"\s+", " ", pair).strip()
        parts = clean_pair.split()
        if len(parts) < 2:
            continue

        first = parts[0]
        # Check if ANY part of the phrase (except the first) is a known surname
        canonical = None
        matched_part = None
        for part in parts[1:]:
            last_variants = [part]
            if "-" in part:
                last_variants.extend(part.split("-"))

            for variant in sorted(last_variants, key=len, reverse=True):
                if len(variant) >= 4 and variant in _KNOWN_SURNAMES:
                    canonical = _KNOWN_SURNAMES[variant]
                    matched_part = part
                    break
            if canonical:
                break

        # Fallback for very specific high-profile mixups
        if not canonical:
            if first == "Bujar" and ("Siljanovska" in clean_pair or "Siljanovska" in clean_pair):
                canonical = "Gordana Siljanovska-Davkova"
                matched_part = parts[-1]

        if canonical:
            canonical_parts = canonical.split()
            # Canonical's last part (might be hyphenated)
            canonical_last = canonical_parts[-1]

            # Improvement: Replace if first name is wrong OR if surname is an alias/variant (like Osmanoska)
            is_wrong_first = first != canonical_parts[0] and first in _KNOWN_FIRSTNAMES

            # Special logic for Bujar + Siljanovska
            if first == "Bujar" and ("Siljanovska" in (matched_part or "") or "Siljanovska" in (matched_part or "")):
                is_wrong_first = True
                canonical = "Gordana Siljanovska-Davkova"

            is_alias_surname = matched_part != canonical_last

            if is_wrong_first or is_alias_surname:
                # Use word boundaries and ensure we match the ENTIRE pair
                pattern = rf"(?<![A-Za-z\u0400-\u04FF-]){re.escape(clean_pair)}(?![A-Za-z\u0400-\u04FF-])"
                if re.search(pattern, joined_text):
                    joined_text = re.sub(pattern, canonical, joined_text)
                    log.info(f"[entities/fix] Hallucination detected: {clean_pair} -> {canonical}")

    if is_list:
        return joined_text.split("\n")
    return joined_text


def normalize_entity_name(name: str) -> str:
    clean = str(name or "").strip()
    if not clean:
        return ""
    if any(ord(c) >= 0x0400 for c in clean):
        from core.language import transliterate_cyr_to_lat
        try:
            clean = transliterate_cyr_to_lat(clean)
        except Exception:
            pass
    
    res = _ENTITY_ALIASES_CASEFOLDED.get(clean.casefold())
    if res:
        return res
        
    # Try diacritic-stripped fallback
    stripped = clean.lower()
    for src, dst in [("ć", "c"), ("č", "c"), ("š", "s"), ("ž", "z"), ("đ", "dj"), ("đ", "d")]:
        stripped = stripped.replace(src, dst)
        
    res = _ENTITY_ALIASES_CASEFOLDED.get(stripped)
    if res:
        return res
        
    return clean



def _is_name_like_phrase(candidate: str) -> bool:
    parts = [part for part in re.split(r"[\s-]+", str(candidate or "").strip()) if part]
    # Handle up to 4 words for names like Ursula von der Leyen
    if len(parts) < 2 or len(parts) > 4:
        return False
    if any(part in IGNORE_WORDS for part in parts):
        return False
    for part in parts:
        if len(part) < 2:  # "von der" uses short words
            return False
        if not re.match(r"^[A-Za-z\u0400-\u04FF][A-Za-z\u0400-\u04FF'.-]*$", part):
            # Allow lowercase parts for particles like 'von', 'der' if already passed IGNORE_WORDS
            # but usually regex fallback captures capitalized words.
            pass
    return True


def determine_relationship_direction(ent_a_name: str, ent_a_type: str, ent_b_name: str, ent_b_type: str, context_text: str) -> str:
    """
    Zero-token heuristic to determine influence direction between two entities in a given text.
    Returns: 'a_to_b', 'b_to_a', or 'mutual'.
    """
    if not context_text:
        return "mutual"

    # Case-insensitive search for first occurrence index
    text_lower = context_text.lower()
    
    # Extract 5-char prefix stems to handle Cyrillic/Latin declensions (e.g. Skupština -> Skupštinu, Vlada -> Vladu)
    def get_stem(name):
        name_clean = (name or "").strip()
        if len(name_clean) >= 5:
            return name_clean[:5].lower()
        return name_clean.lower()

    stem_a = get_stem(ent_a_name)
    stem_b = get_stem(ent_b_name)

    idx_a = text_lower.find(stem_a) if stem_a else -1
    idx_b = text_lower.find(stem_b) if stem_b else -1

    # 1. Type-based hierarchy: PERSON is usually an active agent influencing ORG, LOC or EVENT.
    # If one is a PERSON and the other is not, the PERSON is more likely to be the initiator of the flow.
    type_a = (ent_a_type or "").upper()
    type_b = (ent_b_type or "").upper()
    
    if type_a == "PERSON" and type_b != "PERSON":
        return "a_to_b"
    if type_b == "PERSON" and type_a != "PERSON":
        return "b_to_a"

    # 2. Textual order/prominence heuristic:
    # Check first appearance in text. Initiator is usually mentioned first in broadsheet reporting.
    if idx_a != -1 and idx_b != -1:
        if idx_a < idx_b:
            return "a_to_b"
        elif idx_b < idx_a:
            return "b_to_a"

    # 3. Default fallback if positions are unavailable or equal
    return "mutual"


def update_knowledge_graph(entities: list[dict], context_text: str = ""):
    """
    Updates the global knowledge graph with seen entities and their relationships.
    """
    from core.database import db_manager as db
    from nlp import analyze_sentiment_locally

    if not entities:
        return

    sentiment = analyze_sentiment_locally(context_text, bypass_llm=True) if context_text else 0.0

    entity_info = {}
    for ent in entities:
        # Resolve to canonical name before DB update
        canonical_name = normalize_entity_name(ent["name"])
        entity_info[canonical_name] = (canonical_name, ent.get("type", "ENTITY"))

        sql = """
            INSERT INTO knowledge_entities (name, type, total_mentions, last_seen, sentiment_score)
            VALUES (%s, %s, 1, CURRENT_TIMESTAMP, %s)
            ON CONFLICT (name) DO UPDATE SET
                total_mentions = knowledge_entities.total_mentions + 1,
                last_seen = EXCLUDED.last_seen,
                sentiment_score = (knowledge_entities.sentiment_score * 0.8) + (EXCLUDED.sentiment_score * 0.2)
        """
        db.execute(sql, (canonical_name, ent["type"], sentiment), fetch=False)

    if len(entities) > 1:
        # Sort key names to maintain consistent undirected row keys (a < b)
        sorted_names = sorted(list(entity_info.keys()))
        for i in range(len(sorted_names)):
            for j in range(i + 1, len(sorted_names)):
                a, b = sorted_names[i], sorted_names[j]
                
                a_name, a_type = entity_info[a]
                b_name, b_type = entity_info[b]
                
                direction = determine_relationship_direction(a_name, a_type, b_name, b_type, context_text)
                
                count_a_to_b = 0
                count_b_to_a = 0
                if direction == "a_to_b":
                    count_a_to_b = 1
                elif direction == "b_to_a":
                    count_b_to_a = 1
                else:
                    count_a_to_b = 1
                    count_b_to_a = 1

                sql = """
                    INSERT INTO knowledge_relationships (entity_a, entity_b, weight, count_a_to_b, count_b_to_a, last_seen)
                    VALUES (%s, %s, 1, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (entity_a, entity_b) DO UPDATE SET
                        weight = knowledge_relationships.weight + 1,
                        count_a_to_b = knowledge_relationships.count_a_to_b + EXCLUDED.count_a_to_b,
                        count_b_to_a = knowledge_relationships.count_b_to_a + EXCLUDED.count_b_to_a,
                        last_seen = EXCLUDED.last_seen
                """
                db.execute(sql, (a, b, count_a_to_b, count_b_to_a), fetch=False)


def extract_entities(text: str, max_entities: int = 5) -> list[dict]:
    """
    Extracts entities (PERSON, ORG, LOC) from text using a hybrid approach:
    curated lexicon → spaCy NER → regex fallback.
    """
    if not text:
        return []

    found = {}  # name -> type

    # 1. Exact matching against the curated lexicon (highest precision)
    for name, etype in _KNOWN_ENTITIES_ORDERED:
        if name in text:
            found[name] = etype
    for alias, canonical in _ENTITY_ALIASES_ORDERED:
        if alias in text and canonical in KNOWN_ENTITIES:
            found[canonical] = KNOWN_ENTITIES[canonical]

    # 2. spaCy multilingual NER — catches novel entities the lexicon misses
    nlp = _get_spacy()
    if nlp is not None and len(found) < max_entities + 5:
        try:
            doc = nlp(text[:5000])  # cap length defensively
            for ent in doc.ents:
                if len(found) >= max_entities + 5:
                    break
                name = ent.text.strip()
                if not name or len(name) < 3:
                    continue
                if name in IGNORE_WORDS:
                    continue
                mapped = _SPACY_LABEL_MAP.get(ent.label_, "ENTITY")
                if mapped == "PERSON" and not (
                    _is_name_like_phrase(name) or name in ENTITY_ALIASES or name in KNOWN_ENTITIES
                ):
                    continue
                # Prefer the curated type if we already matched this name
                if name in found:
                    continue
                found[name] = mapped
        except Exception as e:
            log.warning(f"[entities] spaCy NER failed, falling back: {e}")

    # 3. Regex fallback — only if we still need more and spaCy didn't fire
    if len(found) < max_entities:
        candidates = PROPER_NOUN_PATTERN.findall(text)
        for c in candidates:
            if len(found) >= max_entities + 5:
                break
            if c in found or c in IGNORE_WORDS:
                continue
            if len(c) < 4:
                continue
            if _is_name_like_phrase(c):
                found[c] = "ENTITY"
            elif c in ENTITY_ALIASES or c in KNOWN_ENTITIES:
                found[c] = KNOWN_ENTITIES.get(c, "ENTITY")
            elif text.count(c) > 1 and c in ENTITY_ALIASES:  # Repeated known alias only
                found[c] = "ENTITY"

    # Convert to requested format and limit
    result = []
    for name, etype in found.items():
        canonical_name = normalize_entity_name(name)

        # Avoid duplicates if multiple variants resolved to the same canonical name
        if any(r["name"] == canonical_name for r in result):
            continue

        result.append({"name": canonical_name, "type": etype})
        if len(result) >= max_entities:
            break

    return result
