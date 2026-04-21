"""
categories.py — Article categorization for Пресек
Allowed categories (exactly 6, geographic):
  Македонија = domestic news, default fallback
  Балкан     = Serbia, Kosovo, Albania, Greece, Bulgaria, Montenegro,
               Bosnia, Croatia, Turkey
  Европа     = EU / European news (excluding Germany)
  Германија  = Germany standalone
  Америка    = USA + Canada
  Свет       = everything else (Australia, Asia, Africa, Middle East, etc.)
"""
import re
import html

ALLOWED_CATEGORIES = {
    "Македонија", "Балкан", "Европа", "Германија", "Америка", "Свет",
}

THEMATIC_TOPICS = {
    "Политика", "Економија", "Технологија", "Спорт", "Забава", "Здравје", "Вести", "Криминал", "Живот",
}


def _keyword_matches(text: str, keyword: str) -> bool:
    keyword = str(keyword or "").strip().lower()
    if not keyword:
        return False
    # Use word boundaries that support Cyrillic
    pattern = r"(?<![А-Яа-яЀ-ӿ\w])" + re.escape(keyword) + r"(?![А-Яа-яЀ-ӿ\w])"
    return bool(re.search(pattern, text))


def _score_keyword_group(text: str, keywords: list[str]) -> float:
    score = 0.0
    for kw in sorted(keywords, key=len, reverse=True):
        if not _keyword_matches(text, kw):
            continue
        if " " in kw:
            score += 2.5 # Multi-word matches are very strong signals
        elif len(kw) >= 8:
            score += 1.5
        else:
            score += 1.0
    return score


def validate_category(category: str) -> str:
    """Return category if it is in the allowed list, else default to 'Македонија'."""
    return category if category in ALLOWED_CATEGORIES else "Македонија"


# ORDER MATTERS — first match wins.
# Германија before Европа (Germany would otherwise match broad European keywords).
# Балкан before Свет (Balkan countries would otherwise match global keywords).
CATEGORIES = [

    ("Германија", [
        "германија", "германски", "германска", "германскиот",
        "берлин", "хамбург", "минхен", "франкфурт", "кельн", "штутгарт",
        "бундестаг", "бундесрат", "бундесвер",
        "шолц", "мерц", "меркел", "баерн", "дортмунд",
        "germany", "berlin", "scholz",
    ]),

    ("Балкан", [
        "србија", "српски", "белград", "вучиќ", "дачиќ", "брнaбиќ", "павловиќ",
        "бугарија", "бугарски", "софија", "радев", "главчев", "борисов", "петков",
        "грција", "грчки", "атина", "мицотакис", "каселакис", "ципрас",
        "албанија", "тирана", "рама", "бериша", "мета",
        "косово", "приштина", "курти", "османи", "конјуфца",
        "хрватска", "загреб", "милановиќ", "пленковиќ",
        "босна", "сараево", "додик", "беќировиќ", "комшиќ",
        "црна гора", "подгорица", "спајиќ", "милатoвиќ", "абазовиќ",
        "турција", "турски", "анкара", "ердоган", "истанбул", "фидан",
        "балкан", "балкански",
        "serbia", "bulgaria", "greece", "albania", "kosovo", "croatia", "turkey",
    ]),

    ("Америка", [
        "соединети американски држави", "сад", "американски", "америка",
        "вашингтон", "белата куќа", "конгрес на сад", "капитол",
        "трамп", "харис", "бајден", "пентагон", "стејт департмент",
        "волстрит", "силиконска долина", "фбр", "циа",
        "канада", "канадски", "отава", "торонто", "тридо",
        "united states", "washington", "white house", "congress", "trump", "biden",
    ]),

    ("Европа", [
        "европска унија", "европарламент", "европска комисија",
        "брисел", "стразбур", "фон дер лајен", "борел", "мецола",
        "франција", "француски", "париз", "макрон", "ле пен", "атал",
        "велика британија", "британски", "лондон", "обединето кралство", "стармер", "сунак",
        "италија", "италијански", "рим", "мелони", "салвини",
        "шпанија", "шпански", "мадрид", "санчез", "феихо",
        "полска", "полски", "варшава", "туск", "дуда",
        "холандија", "амстердам", "вилдeрс", "руте",
        "белгија", "португалија", "чешка", "унгарија", "австрија",
        "шведска", "норвешка", "данска", "финска",
        "еврозона", "шенген", "европски совет", "европски суд",
        "european union", "european commission", "brussels", "euro",
    ]),

    ("Македонија", [
        "македонија", "македонски", "скопје", "битола", "охрид", "тетово", "куманово",
        "владата", "собранието", "претседателот", "министерството",
        "мицкоски", "сиљановска", "давкова", "ахмети", "филипче", "апасиев", "меџити", "таравари",
        "сдсм", "вмро-дпмне", "дуи", "левица", "знам", "вреди", "европски фронт",
    ]),

    ("Свет", [
        "русија", "руски", "москва", "путин", "кремљ", "лавров", "медведев",
        "украина", "украински", "киев", "зеленски", "кулеба",
        "кина", "кинески", "пекинг", "си џинпинг",
        "јапонија", "јапонски", "токио",
        "индија", "индиски", "њу делхи", "моди",
        "израел", "израелски", "тел авив", "нетанјаху", "палестина", "газа", "хамас", "рафа",
        "иран", "ирански", "техеран", "хаменеи",
        "сирија", "дамаск", "ирак", "авганистан", "талибанци",
        "северна кореја", "пјонгјанг", "ким џонг ун",
        "блискиот исток", "блиски исток",
        "африка", "африкански", "египет", "каиро",
        "австралија", "австралиски",
        "бразил", "мексико", "аргентина",
        "оон", "светска здравствена организација", "сзо", "унмик", "кфор",
        "светски", "светска",
        "нато", "столтенберг",
        "г7", "г20", "брикс",
        "тероризам", "санкции", "мигранти", "бегалци",
        "воена операција", "воени сили", "војна",
        "ракетен напад", "ракети", "бомбардирање",
        "middle east", "united nations", "nato", "russia", "ukraine",
    ]),
]


def detect_category(title: str, description: str = "", source: str = "",
                    forced_category: str | None = None) -> str:
    """Return category for an article.

    If forced_category is provided (e.g. hardcoded at feed level) and valid,
    it is returned immediately without keyword scanning.
    Falls back to 'Македонија' if nothing matches.
    """
    if forced_category and forced_category in ALLOWED_CATEGORIES:
        return forced_category
    text = (title + " " + description).lower()
    best_category = None
    best_score = 0.0
    for cat_name, keywords in CATEGORIES:
        score = _score_keyword_group(text, keywords)
        if score > best_score:
            best_category = cat_name
            best_score = score
    if best_category and best_score >= 1.0:
        return best_category
    return "Македонија"


# ── Sub-categories (regional) ──────────────────────────────────────
SUB_CATEGORIES = [
    ("Скопје", [
        "скопје", "скопски", "град скопје", "градоначалник", "арсовска",
        "аеродром скопје", "карпош", "центар", "гази баба", "аеродром",
        "чаир", "бутел", "кисела вода", "ѓорче петров", "ѓорче",
        "шуто оризари", "сарај", "арачиново", "кисела вода",
        "волково", "драчево", "лисиче", "автокоманда", "железара",
    ]),
    ("Република", [
        "битола", "охрид", "прилеп", "куманово", "тетово",
        "штип", "велес", "кавадарци", "гевгелија", "струмица",
        "кочани", "берово", "делчево", "крива паланка",
        "гостивар", "дебар", "кичево", "струга",
        "свети николе", "неготино", "радовиш", "виница",
        "македонска каменица", "демир хисар", "ресен",
        "пробиштип", "крушево", "валандово", "кратово",
        "демир капија", "пехчево", "дојран", "маврово",
    ]),
]


def detect_subcategory(title: str, description: str = "") -> str | None:
    """Detect optional sub-category (regional). Returns None if no match."""
    text = (title + " " + description).lower()
    for sub_name, keywords in SUB_CATEGORIES:
        if any(_keyword_matches(text, kw) for kw in keywords):
            return sub_name
    return None


# ── Source country code map ────────────────────────────────────────
# ISO 3166-1 alpha-2 codes where applicable; region sentinels for aggregates.
_COUNTRY_MAP: dict[str, str] = {
    # Balkan sources
    "N1 Info":        "RS",
    "Kurir.rs":       "RS",
    "Danas.rs":       "RS",
    "Dnevnik.bg":     "BG",
    "24 Chasa BG":    "BG",
    "Capital.bg":     "BG",
    "Index.hr":       "HR",
    "Jutarnji":       "HR",
    "Klix.ba":        "BA",
    "Vijesti.me":     "ME",
    "RTCG":           "ME",
    "Telegrafi KS":   "XK",
    "Daily Sabah":    "TR",
    "Anadolu Agency": "TR",
    "Balkan Insight": "BALKAN",
    # International sources
    "Tagesschau":     "DE",
    "CNN":            "US",
    "BBC News":       "GB",
    "Reuters":        "GB",
}


# ── Thematic Topic Detection ──────────────────────────────────────

TOPICS = [
    ("Спорт", [
        "фудбал", "кошарка", "ракомет", "тенисер", "тенисерка", "атлетика",
        "лига на шампиони", "премиер лига", "фифа", "уефа", "олимписки", "олимпијада",
        "натпревар", "првенство", "куп", "резултати", "клуб", "играч",
        "трансфер", "гол", "победа", "пораз", "тренер", "селектор",
        "reprezentacija", "гренд слем", "нокаут", "финале", "полуфинале",
        "кошаркар", "фудбалер", "ракометар", "бокс", "формула 1", "ф1", "мото гп",
        "вардар", "пелистер", "шкупи", "шут", "кош", "сет", "меч",
        "football", "basketball", "tennis", "champions league",
    ]),
    ("Технологија", [
        "технологија", "паметен телефон", "смартфон",
        "апликација", "софтвер", "хардвер", "интернет", "сајбер", "хакер", "напад",
        "криптовалути", "биткоин", "блокчеин", "вселена", "ракета", "наса", "илoн маск",
        "иновација", "робот", "чип", "процесор", "мајкрософт", "гугл", "епл", "самсунг",
        "фејсбук", "мета", "твитер", "х", "социјални мрежи", "гејминг", "конзола", "плејстејшн",
        "software", "hardware", "ai", "artificial intelligence", "iphone", "android",
    ]),
    ("Економија", [
        "економија", "финансии", "буџет", "инфлација", "каматна стапка", "камати",
        "берза", "акции", "инвестиции", "банка", "бруто домашен производ", "бдп",
        "данок", "плата", "минимална плата", "пензија", "пазар", "цени", "нафта", "енергија",
        "гас", "криза", "бизнис", "компанија", "корпорација", "трговија", "увоз", "извоз",
        "inflation", "tariffs", "market", "markets", "economy", "budget", "finance", "gdp",
    ]),
    ("Здравје", [
        "здравје", "медицина", "болест", "вирус", "пандемија", "вакцина", "ковид",
        "лекари", "болница", "клиника", "терапија", "здравствен", "лекови",
        "симптоми", "дијагноза", "исхрана", "витамини", "фитнес", "ментално",
        "операција", "пациент", "пациенти", "аптека", "рецепт",
        "hospital", "virus", "vaccine", "health", "medical",
    ]),
    ("Забава", [
        "забава", "музика", "филм", "кино", "холивуд", "актер", "актерка",
        "пејач", "пејачка", "концерт", "албум", "сцена", "култура", "уметност",
        "театар", "изложба", "мода", "стил", "ѕвезда", "славни", "шоу", "евровизија",
        "оскар", "греми", "фестивал", "премиера", "ревија",
        "movie", "music", "film", "show", "celebrity", "entertainment",
    ]),
    ("Криминал", [
        "криминал", "убиство", "кражба", "напад", "полиција", "мвр", "апсење",
        "уапсен", "уапсени", "притвор", "суд", "судење", "пресуда", "затвор",
        "дрога", "оружје", "инцидент", "престрелка", "крв", "тепачка",
        "обвинителство", "обвинет", "осомничен", "измама", "корупција",
        "crime", "murder", "police", "arrest", "investigation",
    ]),
    ("Живот", [
        "живот", "стил", "храна", "патување", "туризам", "одмор", "семејство",
        "деца", "образование", "училиште", "факултет", "студенти", "наука",
        "време", "прогноза", "сонце", "дожд", "снег", "автомобили", "возила",
        "сообраќај", "несреќа", "патни", "превоз", "животни", "природа",
        "lifestyle", "travel", "family", "education", "weather",
    ]),
    ("Политика", [
        "политика", "влада", "министер", "претседател", "парламент", "собрание",
        "избори", "гласање", "партија", "сдсм", "вмро-дпмне", "дуи", "левица", "знам", "вреди",
        "закон", "реформа", "дипломатија", "амбасадор", "протест", "дебата",
        "самит", "договор", "лидер", "политички", "државен", "функционер",
        "мицкоски", "сиљановска", "давкова", "ахмети", "филипче", "апасиев",
        "government", "president", "parliament", "minister", "election", "summit", "politics",
    ]),
]


def detect_topic(title: str, description: str = "") -> str:
    """Detect thematic topic (Sport, Tech, Economy, etc.). Defaults to 'Вести'."""
    text = (title + " " + description).lower()
    best_topic = None
    best_score = 0.0
    for topic_name, keywords in TOPICS:
        score = _score_keyword_group(text, keywords)
        if score > best_score:
            best_topic = topic_name
            best_score = score
    if best_topic and best_score >= 2.0:
        return best_topic
    return "Вести"


def detect_country(source_name: str) -> str:
    """Return the ISO country code for a given source name. Defaults to MK."""
    return _COUNTRY_MAP.get(source_name, "MK")


def normalize_headline(title: str) -> str:
    """Clean up and professionalize news titles for a high-end editorial feel."""
    if not title: return ""
    
    # 1. Preliminary Cleaning
    t = html.unescape(title)
    t = re.sub(r'<[^>]+>', '', t) # Strip HTML
    
    # 2. Aggressive Tag & Decorative Prefix Removal
    # Handles (ВИДЕО), [ФОТО], ЖИВО:, BREAKING:, etc.
    tags_pattern = r'(\[(ВИДЕО|ФОТО|ГАЛЕРИЈА|БРИФИНГ|VIDEO|PHOTO|GALLERY|LIVE)\]|\((ВИДЕО|ФОТО|ГАЛЕРИЈА|БРИФИНГ|VIDEO|PHOTO|GALLERY|LIVE)\))'
    t = re.sub(tags_pattern, '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(ВИДЕО|ФОТО|ГАЛЕРИЈА|БРИФИНГ|VIDEO|PHOTO|GALLERY|LIVE|УЖИВО)[\s\|:–—-]+', '', t, flags=re.IGNORECASE)
    
    sensationalist = [
        "БРЕЈКИНГ", "ЕКСКЛУЗИВНО", "ПОТВРДЕНО", "СКАНДАЛ", "УЖАС", "ТРАГЕДИЈА", 
        "ВО ЖИВО", "ИНТЕРВЈУ", "АНАЛИЗА", "СТРАВИЧНО", "ШОКАНТНО", "НЕВЕРОЈАТНО", 
        "ГЛЕДАЈТЕ", "ВЕЧЕР", "МАКФАКС", "ФОКУС", "ДЕНЕШЕН", "КУРИР", "РЕПУБЛИКА",
        "BREAKING", "EXCLUSIVE", "LIVE", "ОТКРИВАМЕ", "НОВО", "ИТНО", "ВНИМАНИЕ"
    ]
    prefix_pattern = r'^(' + '|'.join(sensationalist) + r')[\s\|:–—-]+'
    t = re.sub(prefix_pattern, '', t, flags=re.IGNORECASE)

    # 3. Suffix / Source Attribution Cleanup
    # Remove things like "- ПРЕСЕК", "| 360 степени" at the end
    sources = [
        "360 степени", "Слободен печат", "Макфакс", "Фокус", "Канал 5", "Сител", "Телма", 
        "МРТ", "A1on", "Локално", "Lokalno", "Вечер", "Vecer", "Nezavisen", "Независен", 
        "Republika", "Република", "Курир", "Kurir", "Денешен", "Denesen", "Meta.mk", 
        "МЕТА", "Плусинфо", "Plusinfo", "Сакам да кажам", "SDK", "SDK.mk", "Deutsche Welle", 
        "DW", "DW.com", "Радио Слободна Европа", "RSE", "РСЕ", "Нова Македонија", "Брифинг"
    ]
    suffix_pattern = r'[\s\|:–—-]+(' + '|'.join(sources) + r')$'
    t = re.sub(suffix_pattern, '', t, flags=re.IGNORECASE)

    # 4. De-Shouting (Sentence Case)
    # If the headline is mostly uppercase (screaming), normalize it
    # We ignore short words to protect acronyms like ЕУ, НАТО, САД
    upper_count = sum(1 for c in t if c.isupper())
    alpha_count = sum(1 for c in t if c.isalpha())
    if alpha_count >= 6 and (upper_count / alpha_count) > 0.65:
        # Convert to sentence case but try to preserve common acronyms
        t = t.capitalize()
        # Restore common Macedonian acronyms (this is a heuristic)
        for acronym in ["ЕУ", "НАТО", "САД", "МВР", "СЗО", "СДСМ", "ВМРО", "ДУИ", "ЗНАМ", "ДИК", "СЕП"]:
            t = re.sub(rf'\b{re.escape(acronym)}\b', acronym, t, flags=re.IGNORECASE)

    # 5. Macedonian Quote Standardization
    # Convert "...", '...', and other variants to literary „...“
    # Handle double single quotes often found in portals
    t = t.replace("''", '"')
    # Use standard Macedonian literary quotes
    t = re.sub(r'["\']([^"\']+)["\']', r'„\1“', t)

    # 6. Technical Polish
    t = re.sub(r'[\?\!]{2,}', lambda m: m.group(0)[0], t) # No !!! or ???
    t = " ".join(t.split()) # Standardize whitespace
    t = t.strip(" -–—:|") # Remove trailing/leading decorations
    
    # 7. Professional Casing for first letter (if not already handled by de-shouting)
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    
    return t.strip()
