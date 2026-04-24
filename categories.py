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
    "Политика", "Економија", "Технологија", "Спорт", "Забава", "Култура", "Здравје", "Вести", "Криминал", "Живот",
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
        elif len(kw) >= 7: # Lowered from 8 to catch 'Владата', 'Партија', etc.
            score += 1.5
        else:
            score += 1.0
    return score


def validate_category(category: str) -> str:
    """Return category if it is in the allowed list, else default to 'Македонија'."""
    return category if category in ALLOWED_CATEGORIES else "Македонија"


# ORDER MATTERS — first match wins.
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
        "нба", "млс", "лејкерс", "хјустон", "мајами хит", "голден стајт",
        "лос анџелес", "интер мајами",
        "united states", "washington", "white house", "congress", "trump", "biden",
        "nba", "mls", "lakers", "houston", "inter miami",
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
        "челзи", "арсенал", "ливерпул", "манчестер јунајтед", "манчестер сити",
        "тотенхем", "псж", "пари сен жермен", "реал мадрид", "барселона",
        "атлетико", "јувентус", "милан", "интер", "наполи", "рома",
        "бенфика", "порто", "спортинг", "ајакс", "псв",
        "european union", "european commission", "brussels", "euro",
        "chelsea", "arsenal", "liverpool", "manchester united", "manchester city",
        "tottenham", "psg", "paris saint-germain", "real madrid", "barcelona",
        "atletico", "juventus", "milan", "inter", "napoli", "roma",
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

TITLE_PROPER_NOUNS = [
    (re.compile(r"\bсрпската опозиција\b", re.IGNORECASE), "Српската опозиција"),
    (re.compile(r"\bиран\b", re.IGNORECASE), "Иран"),
    (re.compile(r"\bданска\b", re.IGNORECASE), "Данска"),
    (re.compile(r"\bевропа\b", re.IGNORECASE), "Европа"),
    (re.compile(r"\bјугославија\b", re.IGNORECASE), "Југославија"),
    (re.compile(r"\bмакедонија\b", re.IGNORECASE), "Македонија"),
    (re.compile(r"\bбугарија\b", re.IGNORECASE), "Бугарија"),
    (re.compile(r"\bсрбија\b", re.IGNORECASE), "Србија"),
    (re.compile(r"\bгрција\b", re.IGNORECASE), "Грција"),
    (re.compile(r"\bалбанија\b", re.IGNORECASE), "Албанија"),
    (re.compile(r"\bкосово\b", re.IGNORECASE), "Косово"),
    (re.compile(r"\bрусија\b", re.IGNORECASE), "Русија"),
    (re.compile(r"\bукраина\b", re.IGNORECASE), "Украина"),
    (re.compile(r"\bизраел\b", re.IGNORECASE), "Израел"),
    (re.compile(r"\bпалестина\b", re.IGNORECASE), "Палестина"),
    (re.compile(r"\bгерманија\b", re.IGNORECASE), "Германија"),
    (re.compile(r"\bфранција\b", re.IGNORECASE), "Франција"),
    (re.compile(r"\bбританска\b", re.IGNORECASE), "Британска"),
    (re.compile(r"\bбританскиот\b", re.IGNORECASE), "Британскиот"),
    (re.compile(r"\bбританија\b", re.IGNORECASE), "Британија"),
    (re.compile(r"\bкина\b", re.IGNORECASE), "Кина"),
    (re.compile(r"\bпекинг\b", re.IGNORECASE), "Пекинг"),
    (re.compile(r"\bси џинпинг\b", re.IGNORECASE), "Си Џинпинг"),
    (re.compile(r"\bсад\b", re.IGNORECASE), "САД"),
    (re.compile(r"\bеу\b", re.IGNORECASE), "ЕУ"),
    (re.compile(r"\bнато\b", re.IGNORECASE), "НАТО"),
    (re.compile(r"\bтито\b", re.IGNORECASE), "Тито"),
    (re.compile(r"\bзаев\b", re.IGNORECASE), "Заев"),
    (re.compile(r"\bмицкоски\b", re.IGNORECASE), "Мицкоски"),
    (re.compile(r"\bфилипче\b", re.IGNORECASE), "Филипче"),
    (re.compile(r"\bахмети\b", re.IGNORECASE), "Ахмети"),
    (re.compile(r"\bбашановиќ\b", re.IGNORECASE), "Башановиќ"),
    (re.compile(r"\bбашановик\b", re.IGNORECASE), "Башановиќ"),
    (re.compile(r"\bскопје\b", re.IGNORECASE), "Скопје"),
    (re.compile(r"\bбитола\b", re.IGNORECASE), "Битола"),
    (re.compile(r"\bохрид\b", re.IGNORECASE), "Охрид"),
    (re.compile(r"\bтетово\b", re.IGNORECASE), "Тетово"),
    (re.compile(r"\bштип\b", re.IGNORECASE), "Штип"),
]


def detect_category(title: str, description: str = "", source: str = "", forced_category: str = None) -> str:
    """Return category for an article."""
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
_COUNTRY_MAP: dict[str, str] = {
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
    "Tagesschau":     "DE",
    "CNN":            "US",
    "BBC News":       "GB",
    "Reuters":        "GB",
}


# ── Thematic Topic Detection ──────────────────────────────────────

TOPICS = [
    ("Политика", [
        "политика", "влада", "владата", "министер", "претседател", "парламент", "парламентот", "собрание", "собранието",
        "избори", "гласање", "партија", "сдсм", "вмро-дпмне", "дуи", "левица", "знам", "вреди",
        "закон", "реформа", "дипломатија", "амбасадор", "протест", "протести", "дебата",
        "самит", "договор", "лидер", "политички", "државен", "функционер",
        "мицкоски", "сиљановска", "давкова", "ахмети", "филипче", "апасиев",
        "министерство", "министерството", "институции", "државна",
        "government", "president", "parliament", "minister", "election", "summit", "politics",
    ]),
    ("Економија", [
        "економија", "финансии", "буџет", "инфлација", "каматна стапка", "камати",
        "берза", "акции", "инвестиции", "банка", "бруто домашен производ", "бдп",
        "данок", "плата", "минимална плата", "пензија", "пазар", "цени", "нафта", "енергија",
        "гас", "криза", "мерки", "бизнис", "компанија", "корпорација", "трговија", "увоз", "извоз",
        "фирми", "фирмите", "поддршка", "претпријатија", "субвенции",
        "inflation", "tariffs", "market", "markets", "economy", "budget", "finance", "gdp",
    ]),
    ("Спорт", [
        "фудбал", "кошарка", "ракомет", "тенисер", "тенисерка", "атлетика",
        "лига на шампиони", "премиер лига", "фифа", "уефа", "олимписки", "олимпијада",
        "натпревар", "првенство", "куп", "резултати", "клуб", "играч",
        "трансфер", "гол", "победа", "победи", "пораз", "тренер", "селектор",
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
    ("Здравје", [
        "здравје", "медицина", "болест", "вирус", "пандемија", "вакцина", "ковид",
        "лекари", "болница", "клиника", "терапија", "здравствен", "лекови",
        "симптоми", "дијагноза", "исхрана", "витамини", "фитнес", "ментално",
        "операција", "пациент", "пациенти", "аптека", "рецепт",
        "hospital", "virus", "vaccine", "health", "medical",
    ]),
    ("Култура", [
        "култура", "уметност", "театар", "изложба", "книжевност", "литература",
        "писател", "писателка", "книга", "библиотека", "музеј", "галерија",
        "спектакл", "настан", "фестивал", "културен", "културна", "уметник", "уметница",
        "кино", "филм", "кинотека", "премиера", "архитектура", "дизајн",
        "culture", "art", "museum", "theater", "literature",
    ]),
    ("Забава", [
        "забава", "музика", "холивуд", "актер", "актерка",
        "пејач", "пејачка", "концерт", "албум", "сцена",
        "мода", "стил", "ѕвезда", "славни", "шоу", "евровизија",
        "оскар", "греми", "ревија", "познати", "трач", "свет", "џет-сет",
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
    if best_topic and best_score >= 1.5:
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
    tags_pattern = r'(\[[^\]]*(ВИДЕО|ФОТО|ГАЛЕРИЈА|БРИФИНГ|VIDEO|PHOTO|GALLERY|LIVE)[^\]]*\]|\([^\)]*(ВИДЕО|ФОТО|ГАЛЕРИЈА|БРИФИНГ|VIDEO|PHOTO|GALLERY|LIVE)[^\)]*\))'
    t = re.sub(tags_pattern, '', t, flags=re.IGNORECASE)
    
    # Common prefix labels (standing alone or followed by colon/dash)
    t = re.sub(r'^(ВИДЕО|ФОТО|ГАЛЕРИЈА|БРИФИНГ|VIDEO|PHOTO|GALLERY|LIVE|УЖИВО|НОВО|ИТНО|ВНИМАНИЕ)[\s\|:–—-]+', '', t, flags=re.IGNORECASE)
    
    sensationalist = [
        "БРЕЈКИНГ", "ЕКСКЛУЗИВНО", "ПОТВРДЕНО", "СКАНДАЛ", "УЖАС", "ТРАГЕДИЈА", 
        "ИНТЕРВЈУ", "АНАЛИЗА", "СТРАВИЧНО", "ШОКАНТНО", "НЕВЕРОЈАТНО", 
        "ГЛЕДАЈТЕ", "ВЕЧЕР", "МАКФАКС", "ФОКУС", "ДЕНЕШЕН", "КУРИР", "РЕПУБЛИКА",
        "BREAKING", "EXCLUSIVE", "ОТКРИВАМЕ", "ВОЗНЕМИРУВАЧКО", "ВИДЕОИНТЕРВЈУ",
        "ВИДЕО-ИНТЕРВЈУ"
    ]
    prefix_pattern = r'^(' + '|'.join(sensationalist) + r')[\s\|:–—-]+'
    t = re.sub(prefix_pattern, '', t, flags=re.IGNORECASE)
    
    # Strip any remaining all-caps prefix followed by colon (e.g. "СКОПЈЕ: ...")
    t = re.sub(r'^[А-ЯЁЂЃЄЅІЇЈЉЊЋЌЍЎЏ\s]{3,}:', '', t).strip()

    # 3. Suffix / Source Attribution Cleanup
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
    # Improved check: if more than 65% of alpha chars are uppercase
    # OR if title starts with a long uppercase segment before a colon
    alpha_chars = [c for c in t if c.isalpha()]
    upper_count = sum(1 for c in alpha_chars if c.isupper())
    alpha_count = len(alpha_chars)
    
    # Prefix check like "МАКЕДОНИЈА: Наслов..."
    long_upper_prefix = re.match(r'^([А-ЯЁЂЃЄЅІЇЈЉЊЋЌЍЎЏ\s]{6,}):', t)
    
    if (alpha_count >= 6 and (upper_count / alpha_count) > 0.65) or long_upper_prefix:
        # Before lower-casing, protect common Macedonian/International acronyms
        acronyms = {"ЕУ", "НАТО", "САД", "МВР", "СЗО", "СДСМ", "ВМРО", "ДУИ", "ЗНАМ", "ДИК", "СЕП", "УЈП", "МНР", "МО", "МЗ", "УБК", "ОЈО", "АЕК", "ФФМ", "МОК"}
        
        # Capitalize only first letter, lower the rest
        t_normalized = t.capitalize()
        
        # Restore acronyms
        for acronym in acronyms:
            t_normalized = re.sub(rf'\b{re.escape(acronym)}\b', acronym, t_normalized, flags=re.IGNORECASE)
        t = t_normalized

    # 5. Macedonian Quote Standardization (Standard quotes „...“)
    t = t.replace("''", '"')
    # Replace simple quotes with balanced Macedonian ones
    t = re.sub(r'["\']([^"\']+)["\']', r'„\1“', t)

    # 6. Technical Polish
    t = re.sub(r'[\?\!]{2,}', lambda m: m.group(0)[0], t) # No !!! or ???
    t = " ".join(t.split()) # Standardize whitespace
    t = t.strip(" -–—:|") # Remove trailing/leading decorations
    for pattern, replacement in TITLE_PROPER_NOUNS:
        t = pattern.sub(replacement, t)
    
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    
    return t.strip()
