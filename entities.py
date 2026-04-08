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
    "Христијан Мицкоски": "PERSON",
    "Димитар Ковачевски": "PERSON",
    "Стево Пендаровски": "PERSON",
    "Гордана Силјановска-Давкова": "PERSON",
    "Али Ахмети": "PERSON",
    "Зијадин Села": "PERSON",
    "Арбен Таравари": "PERSON",
    "Максим Димитриевски": "PERSON",
    "Димитар Апасиев": "PERSON",
    "Билал Касами": "PERSON",
    "Венко Филипче": "PERSON",
    "Оливер Спасовски": "PERSON",
    "Бојан Маричиќ": "PERSON",
    "Славјанка Петровска": "PERSON",
    "Артан Груби": "PERSON",
    "Бујар Османи": "PERSON",
    "Тимчо Муцунски": "PERSON",
    "Никола Груевски": "PERSON",
    "Зоран Заев": "PERSON",
    "Бранко Црвенковски": "PERSON",
    "Сашо Мијалков": "PERSON",
    "Јован Митрески": "PERSON",
    "Игор Јанушев": "PERSON",
    "Владо Мисајловски": "PERSON",
    "Фатмир Битиќи": "PERSON",
    "Крешник Бектеши": "PERSON",
    "Љупчо Николовски": "PERSON",
    "Петар Богојески": "PERSON",
    "Дане Талески": "PERSON",
    "Антонио Милошоски": "PERSON",
    "Драган Ковачки": "PERSON",
    "Катерина Цаневска": "PERSON",
    "Миле Лефков": "PERSON",
    "Изет Меџити": "PERSON",
    "Африм Гаши": "PERSON",
    "Халил Снопче": "PERSON",
    
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
    "СЗО": "ORG",
    "Светска здравствена организација": "ORG",
    "ММФ": "ORG",
    "Светска банка": "ORG",
    "Европски парламент": "ORG",
    "Европска комисија": "ORG",
    "Стејт департмент": "ORG",
    "Кремљ": "ORG",
    "Белата куќа": "ORG",
    "Пентагон": "ORG",
    "ЦИА": "ORG",
    "ФБИ": "ORG",
    "УНИЦЕФ": "ORG",
    "ЕЦБ": "ORG",
    "ОБСЕ": "ORG",
    "ХАМАС": "ORG",
    "ОПЕК": "ORG",
    
    # Short names / Aliases
    "Мицкоски": "PERSON",
    "Ковачевски": "PERSON",
    "Пендаровски": "PERSON",
    "Силјановска": "PERSON",
    "Силјановска-Давкова": "PERSON",
    "Трамп": "PERSON",
    "Путин": "PERSON",
    "Вучиќ": "PERSON",
    "Зеленски": "PERSON",
    "Апасиев": "PERSON",
    "Макрон": "PERSON",
    "Курти": "PERSON",
    "ВМРО": "ORG",
    "ВМРО ДПМНЕ": "ORG",
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
    "Трамп": "Доналд Трамп",
    "Путин": "Владимир Путин",
    "Вучиќ": "Александар Вучиќ",
    "Зеленски": "Володимир Зеленски",
    "Апасиев": "Димитар Апасиев",
    "Макрон": "Емануел Макрон",
    "Курти": "Албин Курти",
    "ВМРО": "ВМРО-ДПМНЕ",
    "ВМРО ДПМНЕ": "ВМРО-ДПМНЕ",
    "ОН": "Обединети Нации",
    "СЗО": "Светска здравствена организација",
    "МВР": "Министерство за внатрешни работи",
    "МНР": "Министерство за надворешни работи",
}

def normalize_entity_name(name: str) -> str:
    return ENTITY_ALIASES.get(name, name)

def update_knowledge_graph(entities: list[dict], context_text: str = ""):
    """
    Updates the global knowledge graph with seen entities and their relationships.
    """
    from database import db_manager as db
    from local_nlp import analyze_sentiment_locally

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
    for name, etype in KNOWN_ENTITIES.items():
        if name in text:
            found[name] = etype

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
                # Prefer the curated type if we already matched this name
                if name in found:
                    continue
                mapped = _SPACY_LABEL_MAP.get(ent.label_, "ENTITY")
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
            # Multi-word phrases are likely ORG or PERSON
            if " " in c:
                found[c] = "ENTITY"
            elif text.count(c) > 1:  # Repeated single proper noun
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
