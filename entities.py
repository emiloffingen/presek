"""
entities.py — Hybrid entity extraction for Presek.

Pipeline:
1. Exact-match against the curated KNOWN_ENTITIES lexicon (highest precision)
2. spaCy multilingual NER (`xx_ent_wiki_sm`) when available — catches novel
   people / orgs / locations the lexicon doesn't know about
3. Regex capitalized-phrase heuristic as a final fallback
"""
import re
import logging
import threading
from collections import Counter

log = logging.getLogger("presek")

_spacy_nlp = None
_spacy_lock = threading.Lock()
_spacy_unavailable = False


def _get_spacy():
    """Lazy-load spaCy multilingual NER once per process. Returns None if
    spaCy or the model is unavailable — callers must handle the fallback."""
    global _spacy_nlp, _spacy_unavailable
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
    "Али Ахмети": "PERSON",
    "Антонио Милошоски": "PERSON",
    "Арбен Таравари": "PERSON",
    "Артан Груби": "PERSON",
    "Африм Гаши": "PERSON",
    "Билал Касами": "PERSON",
    "Бојан Маричиќ": "PERSON",
    "Бранко Црвенковски": "PERSON",
    "Бујар Османи": "PERSON",
    "Венко Филипче": "PERSON",
    "Владо Мисајловски": "PERSON",
    "Гордана Силјановска-Давкова": "PERSON",
    "Дане Талески": "PERSON",
    "Димитар Апасиев": "PERSON",
    "Димитар Димовски": "PERSON",
    "Димитар Ковачевски": "PERSON",
    "Драган Ковачки": "PERSON",
    "Зијадин Села": "PERSON",
    "Зоран Заев": "PERSON",
    "Изет Меџити": "PERSON",
    "Игор Јанушев": "PERSON",
    "Јован Митрески": "PERSON",
    "Катерина Цаневска": "PERSON",
    "Крешник Бектеши": "PERSON",
    "Љупчо Николовски": "PERSON",
    "Максим Димитриевски": "PERSON",
    "Миле Лефков": "PERSON",
    "Никола Груевски": "PERSON",
    "Оливер Спасовски": "PERSON",
    "Петар Богојески": "PERSON",
    "Сашо Мијалков": "PERSON",
    "Славјанка Петровска": "PERSON",
    "Стево Пендаровски": "PERSON",
    "Тимчо Муцунски": "PERSON",
    "Фатмир Битиќи": "PERSON",
    "Халил Снопче": "PERSON",
    "Христијан Мицкоски": "PERSON",
    
    # Global - People
    "Доналд Трамп": "PERSON",
    "Џо Бајден": "PERSON",
    "Владимир Путин": "PERSON",
    "Володимир Зеленски": "PERSON",
    "Емануел Макрон": "PERSON",
    "Олаф Шолц": "PERSON",
    "Виктор Орбан": "PERSON",
    "Александар Вучиќ": "PERSON",
    "Киријакос Мицотакис": "PERSON",
    "Реџеп Таип Ердоган": "PERSON",
    "Си Џинпинг": "PERSON",
    "Риши Сунак": "PERSON",
    "Кир Стармер": "PERSON",
    "Камала Харис": "PERSON",
    "Илон Маск": "PERSON",
    "Папата Франциск": "PERSON",
    "Бенјамин Нетанјаху": "PERSON",
    "Роберт Фицо": "PERSON",
    "Ентони Блинкен": "PERSON",
    "Ким Џонг Ун": "PERSON",
    "Мајк Пенс": "PERSON",
    "Џеј Ди Венс": "PERSON",
    "Роберт Кенеди Помладиот": "PERSON",
    "Вивек Рамасвами": "PERSON",
    "Румен Радев": "PERSON",
    "Бојко Борисов": "PERSON",
    "Марк Руте": "PERSON",
    "Педро Санчез": "PERSON",
    "Антонио Гутереш": "PERSON",
    "Урсула фон дер Лајен": "PERSON",
    "Жозеп Борел": "PERSON",
    "Марк Закерберг": "PERSON",
    "Бил Гејтс": "PERSON",
    "Џеф Безос": "PERSON",
    "Џорџ Сорос": "PERSON",

    # Organizations - Domestic
    "Влада": "ORG",
    "Собрание": "ORG",
    "ВМРО-ДПМНЕ": "ORG",
    "СДСМ": "ORG",
    "ДУИ": "ORG",
    "Алијанса за Албанците": "ORG",
    "Левица": "ORG",
    "ЗНАМ": "ORG",
    "Вреди": "ORG",
    "Алтернатива": "ORG",
    "Движење Беса": "ORG",
    "Демократско движење": "ORG",
    "ГРОМ": "ORG",
    "ЛДП": "ORG",
    "МВР": "ORG",
    "Министерство за внатрешни работи": "ORG",
    "Министерство за здравство": "ORG",
    "Министерство за образование": "ORG",
    "Министерство за одбрана": "ORG",
    "Министерство за надворешни работи": "ORG",
    "МНР": "ORG",
    "Министерство за транспорт и врски": "ORG",
    "Министерство за економија": "ORG",
    "Министерство за финансии": "ORG",
    "Министерство за правда": "ORG",
    "Министерство за земјоделство": "ORG",
    "Министерство за култура": "ORG",
    "УЈП": "ORG",
    "Царинска управа": "ORG",
    "Агенција за млади и спорт": "ORG",
    "Град Скопје": "ORG",
    "ЈСП": "ORG",
    "Водовод и канализација": "ORG",
    "Паркови и зеленило": "ORG",
    "Комунална хигиена": "ORG",
    "Судски совет": "ORG",
    "Уставен суд": "ORG",
    "Апелационен суд": "ORG",
    "Кривичен суд": "ORG",
    "Основен суд": "ORG",
    "Врховен суд": "ORG",
    "Државна изборна комисија": "ORG",
    "ДИК": "ORG",
    "Државен завод за статистика": "ORG",
    "ДЗС": "ORG",
    "Агенција за храна и ветеринарство": "ORG",
    "ЕСМ": "ORG",
    "МЕПСО": "ORG",
    "ЕВН": "ORG",
    "АД Електрани": "ORG",
    "Агенција за аудио и аудиовизуелни медиумски услуги": "ORG",
    "АВМУ": "ORG",

    # Organizations - International
    "Европска Унија": "ORG",
    "ЕУ": "ORG",
    "НАТО": "ORG",
    "ОН": "ORG",
    "Обединети Нации": "ORG",
    "Светска здравствена организација": "ORG",
    "СЗО": "ORG",
    "ММФ": "ORG",
    "Светска банка": "ORG",
    "Европска комисија": "ORG",
    "Европски парламент": "ORG",
    "Европска централна банка": "ORG",
    "ЕЦБ": "ORG",
    "Совет на Европа": "ORG",
    "КФОР": "ORG",
    "ФЕД": "ORG",
    "ОБСЕ": "ORG",
    "Хашки трибунал": "ORG",
    "УНИЦЕФ": "ORG",
    "УНЕСКО": "ORG",
    "Амнести интернешнал": "ORG",
    "Црвен крст": "ORG",
    "Стејт департмент": "ORG",
    "Кремљ": "ORG",
    "Белата куќа": "ORG",
    "Пентагон": "ORG",
    "ЦИА": "ORG",
    "ФБИ": "ORG",
    "ХАМАС": "ORG",
    "ОПЕК": "ORG",
    "Ормуз": "LOC",
}

# Regex for detecting Macedonian proper nouns (starts with capital letter)
PROPER_NOUN_PATTERN = re.compile(r"(?:\b[А-ЯЀ-ӿ][а-яѐ-ӿ0-9]+\b(?:[\s-]+\b[А-ЯЀ-ӿ][а-яѐ-ӿ0-9]+\b){0,2})")

# Words to ignore (common words that are capitalized at start of sentence)
IGNORE_WORDS = {
    "Денеска", "Утре", "Вчера", "Повеќе", "Според", "Како", "Ова", "Оваа", "Тоа",
    "Сите", "Нема", "Има", "Беше", "Биде", "Овие", "Никој", "Секој", "Веста",
    "Информација", "Медиумите", "Новите", "Повторно", "Наместо", "Додека",
    "Поради", "Заради", "Иако", "Освен", "Меѓутоа", "Сепак", "Затоа", "Но", "Значи",
    "Кога", "Само", "Она", "Исто", "Истото", "Токму", "Тогаш", "Спротивно",
    "Впрочем", "Меѓу", "Преку", "Во", "На", "За", "Од", "Со", "До",
    "Не", "Да", "Дали", "Прво", "Првиот", "Два", "Три", "Потоа", "После",
}

# Normalize variants to canonical forms
ENTITY_ALIASES = {
    "Мицкоски": "Христијан Мицкоски",
    "Ковачевски": "Димитар Ковачевски",
    "Пендаровски": "Стево Пендаровски",
    "Силјановска": "Гордана Силјановска-Давкова",
    "Силјановска-Давкова": "Гордана Силјановска-Давкова",
    "Сиљановска": "Гордана Силјановска-Давкова",
    "Сиљановска-Давкова": "Гордана Силјановска-Давкова",
    "Трамп": "Доналд Трамп",
    "Путин": "Владимир Путин",
    "Вучиќ": "Александар Вучиќ",
    "Зеленски": "Володимир Зеленски",
    "Апасиев": "Димитар Апасиев",
    "Макрон": "Емануел Макрон",
    "Курти": "Албин Курти",
    "Филипче": "Венко Филипче",
    "Груевски": "Никола Груевски",
    "Јаневска": "Весна Јаневска",
    "Османи": "Бујар Османи",
    "Османоска": "Бујар Османи",
    "ВМРО": "ВМРО-ДПМНЕ",
    "ВМРО ДПМНЕ": "ВМРО-ДПМНЕ",
    "Ормускиот": "Ормуз",
    "Ормутскиот": "Ормуз",
    "ОН": "Обединети Нации",
    "СЗО": "Светска здравствена организација",
    "МВР": "Министерство за внатрешни работи",
    "МНР": "Министерство за надворешни работи",
    # Common Latin-script renderings from international wires
    "Donald Trump": "Доналд Трамп",
    "Joe Biden": "Џо Бајден",
    "Vladimir Putin": "Владимир Путин",
    "Volodymyr Zelenskyy": "Володимир Зеленски",
    "Volodymyr Zelensky": "Володимир Зеленски",
    "Emmanuel Macron": "Емануел Макрон",
    "Olaf Scholz": "Олаф Шолц",
    "Viktor Orban": "Виктор Орбан",
    "Aleksandar Vucic": "Александар Вучиќ",
    "Kyriakos Mitsotakis": "Киријакос Мицотакис",
    "Recep Tayyip Erdogan": "Реџеп Таип Ердоган",
    "Xi Jinping": "Си Џинпинг",
    "Rishi Sunak": "Риши Сунак",
    "Keir Starmer": "Кир Стармер",
    "Kamala Harris": "Камала Харис",
    "Elon Musk": "Илон Маск",
    "Pope Francis": "Папата Франциск",
    "Benjamin Netanyahu": "Бенјамин Нетанјаху",
    "Robert Fico": "Роберт Фицо",
    "Antony Blinken": "Ентони Блинкен",
    "Kim Jong Un": "Ким Џонг Ун",
    "Mark Zuckerberg": "Марк Закерберг",
    "Bill Gates": "Бил Гејтс",
    "Jeff Bezos": "Џеф Безос",
    "George Soros": "Џорџ Сорос",
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

_ENTITY_ALIASES_CASEFOLDED = {
    str(alias).strip().casefold(): canonical
    for alias, canonical in ENTITY_ALIASES.items()
}
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

def validate_person_names(text: str) -> str:
    """
    Heuristic to fix AI hallucinations of famous names.
    If it finds 'Dimitar Filipce' but 'Filipce' is known as 'Venko', and 'Dimitar' is known as 'Kovacevski',
    it checks for likely mixups and restores canonical forms.
    """
    if not text:
        return text
    
    # Look for known surnames with wrong first names
    # Patterns like "Dimitar Filipce" (hallucination)
    # We use a regex that handles hyphenated surnames as a single unit
    words = re.findall(r"\b[А-ЯЀ-ӿ][а-яѐ-ӿ]+\s+[А-ЯЀ-ӿ][а-яѐ-ӿ]+(?:-[А-ЯЀ-ӿ][а-яѐ-ӿ]+)*\b", text)
    for pair in words:
        if pair in KNOWN_ENTITIES: continue
        
        parts = pair.split()
        if len(parts) != 2: continue
        first, last = parts
        
        # Case: Surname is famous (Filipce), but first name is wrong for that person
        if last in _KNOWN_SURNAMES:
            canonical = _KNOWN_SURNAMES[last]
            if first != canonical.split()[0]:
                # Strong signal: is the first name also a famous person's first name? (Dimitar)
                if first in _KNOWN_FIRSTNAMES:
                    # Avoid double names if already partially fixed
                    if canonical in text: continue
                    text = text.replace(pair, canonical)
                    log.info(f"[entities/fix] Hallucination detected: {pair} -> {canonical}")
                    
    return text


def normalize_entity_name(name: str) -> str:
    clean = str(name or "").strip()
    if not clean:
        return ""
    return _ENTITY_ALIASES_CASEFOLDED.get(clean.casefold(), clean)


def _is_name_like_phrase(candidate: str) -> bool:
    parts = [part for part in re.split(r"[\s-]+", str(candidate or "").strip()) if part]
    if len(parts) < 2 or len(parts) > 3:
        return False
    if any(part in IGNORE_WORDS for part in parts):
        return False
    for part in parts:
        if len(part) < 3:
            return False
        if not re.match(r"^[A-ZА-ЯЀ-ӿ][A-Za-zА-Яа-яЀ-ӿѐ-ӿ'.-]+$", part):
            return False
    return True

def update_knowledge_graph(entities: list[dict], context_text: str = ""):
    """
    Updates the global knowledge graph with seen entities and their relationships.
    """
    from database import db_manager as db
    from nlp import analyze_sentiment_locally

    if not entities: return

    sentiment = analyze_sentiment_locally(context_text) if context_text else 0.0

    for ent in entities:
        sql = """
            INSERT INTO knowledge_entities (name, type, total_mentions, last_seen, sentiment_score)
            VALUES (%s, %s, 1, CURRENT_TIMESTAMP, %s)
            ON CONFLICT (name) DO UPDATE SET
                total_mentions = knowledge_entities.total_mentions + 1,
                last_seen = EXCLUDED.last_seen,
                sentiment_score = (knowledge_entities.sentiment_score * 0.7) + (EXCLUDED.sentiment_score * 0.3)
        """
        db.execute(sql, (ent['name'], ent['type'], sentiment), fetch=False)

    if len(entities) > 1:
        sorted_names = sorted([e['name'] for e in entities])
        for i in range(len(sorted_names)):
            for j in range(i + 1, len(sorted_names)):
                a, b = sorted_names[i], sorted_names[j]
                sql = """
                    INSERT INTO knowledge_relationships (entity_a, entity_b, weight, last_seen)
                    VALUES (%s, %s, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT (entity_a, entity_b) DO UPDATE SET
                        weight = knowledge_relationships.weight + 1,
                        last_seen = EXCLUDED.last_seen
                """
                db.execute(sql, (a, b), fetch=False)

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
                if mapped == "PERSON" and not (_is_name_like_phrase(name) or name in ENTITY_ALIASES or name in KNOWN_ENTITIES):
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
        if any(r['name'] == canonical_name for r in result):
            continue
            
        result.append({"name": canonical_name, "type": etype})
        if len(result) >= max_entities:
            break

    return result
