"""
entities.py — Rule-based entity extraction for Presek (Free alternative to AI)
"""
import re
from collections import Counter

# Common Macedonian entities (VIPs) for exact matching
# This list can be expanded over time.
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
    "МВР": "ORG",
    "Министерство за внатрешни работи": "ORG",
    "Министерство за здравство": "ORG",
    "Министерство за образование": "ORG",
    "Министерство за одбрана": "ORG",
    "Министерство за надворешни работи": "ORG",
    "МНР": "ORG",
    "УЈП": "ORG",
    "Агенција за млади и спорт": "ORG",
    "Град Скопје": "ORG",
    "ЈСП": "ORG",
    "КХЛ": "ORG",
    "Судски совет": "ORG",
    "Уставен суд": "ORG",

    # Organizations - International
    "Европска Унија": "ORG",
    "ЕУ": "ORG",
    "НАТО": "ORG",
    "ОН": "ORG",
    "Обединети Нации": "ORG",
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
}

# Regex for detecting Macedonian proper nouns (starts with capital letter)
# Matches words like "Мицкоски", "Скопје", "Македонија"
# Excludes common words at the start of sentences by looking at surrounding context.
PROPER_NOUN_PATTERN = re.compile(r'\b([А-Ш][а-ш]{2,}(?:\s+[А-Ш][а-ш]{2,})?)\b')

# Words to ignore (common words that are capitalized at start of sentence)
IGNORE_WORDS = {
    "Денеска", "Утре", "Вчера", "Повеќе", "Според", "Како", "Ова", "Оваа", "Тоа",
    "Сите", "Нема", "Има", "Беше", "Биде", "Овие", "Никој", "Секој", "Веста",
    "Информација", "Медиумите", "Новите", "Повторно", "Наместо", "Додека",
    "Поради", "Заради", "Иако", "Освен", "Меѓутоа", "Сепак", "Затоа",
}

def update_knowledge_graph(entities: list[dict]):
    \"\"\"
    Updates the global knowledge graph with seen entities and their relationships.
    \"\"\"
    from database import db_manager as db
    import json

    if not entities: return

    # 1. Upsert Entities
    for ent in entities:
        sql = \"\"\"
            INSERT INTO knowledge_entities (name, type, total_mentions, last_seen)
            VALUES (%s, %s, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET
                total_mentions = knowledge_entities.total_mentions + 1,
                last_seen = EXCLUDED.last_seen
        \"\"\"
        db.execute(sql, (ent['name'], ent['type']), fetch=False)

    # 2. Build Relationships (Co-occurrence)
    if len(entities) > 1:
        # Sort to ensure (A, B) is same as (B, A)
        sorted_names = sorted([e['name'] for e in entities])
        for i in range(len(sorted_names)):
            for j in range(i + 1, len(sorted_names)):
                a, b = sorted_names[i], sorted_names[j]
                sql = \"\"\"
                    INSERT INTO knowledge_relationships (entity_a, entity_b, weight, last_seen)
                    VALUES (%s, %s, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT (entity_a, entity_b) DO UPDATE SET
                        weight = knowledge_relationships.weight + 1,
                        last_seen = EXCLUDED.last_seen
                \"\"\"
                db.execute(sql, (a, b), fetch=False)

def extract_entities(text: str, max_entities: int = 5) -> list[dict]:
    """
    Extracts entities (PERSON, ORG) from text using a hybrid approach:
    1. Exact matching against KNOWN_ENTITIES.
    2. Regex heuristic for other proper nouns.
    """
    if not text:
        return []

    found = {} # name -> type

    # 1. Exact matching (Priority)
    for name, etype in KNOWN_ENTITIES.items():
        if name in text:
            found[name] = etype

    # 2. Regex heuristics for others if we have room
    if len(found) < max_entities:
        candidates = PROPER_NOUN_PATTERN.findall(text)
        # Filter candidates
        for c in candidates:
            if len(found) >= max_entities + 3: # Get a few extra to pick the best
                break
            if c in found or c in IGNORE_WORDS:
                continue
            # If it looks like a single common word, skip
            if len(c) < 4:
                continue
            
            # Simple heuristic: if it's not in KNOWN_ENTITIES but looks like a proper noun
            # we default to a generic "ENTITY" or try to guess.
            # For simplicity, we only add if it appears multiple times or is multi-word.
            if " " in c: # Multi-word is likely a name/org
                found[c] = "ENTITY"
            elif text.count(c) > 1: # Mentioned multiple times
                found[c] = "ENTITY"

    # Convert to requested format and limit
    result = []
    for name, etype in found.items():
        result.append({"name": name, "type": etype})
        if len(result) >= max_entities:
            break
            
    return result
