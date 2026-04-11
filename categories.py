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
    ]),

    ("Балкан", [
        "србија", "српски", "белград", "вучиќ", "дачиќ", "брнaбиќ",
        "бугарија", "бугарски", "софија", "радев", "главчев", "борисов",
        "грција", "грчки", "атина", "мицотакис", "каселакис",
        "албанија", "тирана", "рама", "бериша",
        "косово", "приштина", "курти", "османи",
        "хрватска", "загреб", "милановиќ", "пленковиќ",
        "босна", "сараево", "додик", "беќировиќ",
        "црна гора", "подгорица", "спајиќ", "милатoвиќ",
        "турција", "турски", "анкара", "ердоган", "истанбул",
        "балкан", "балкански",
        "северна македонија и",  # regional framing ("Н. Македонија и Србија")
    ]),

    ("Америка", [
        "соединети американски држави", "сад", "американски", "америка",
        "вашингтон", "белата куќа", "конгрес на сад", "капитол",
        "трамп", "харис", "бајден", "пентагон", "стејт департмент",
        "волстрит", "силиконска долина", "фбр", "циа",
        "канада", "канадски", "отава", "торонто", "тридо",
        "united states", "washington", "white house", "congress", "trump", "biden",
    ]),

    # Европа comes after Германија — Germany keywords are already caught above.
    ("Европа", [
        "европска унија", "европарламент", "европска комисија",
        "брисел", "стразбур", "фон дер лајен", "борел",
        "франција", "француски", "париз", "макрон", "ле пен",
        "велика британија", "британски", "лондон", "обединето кралство", "стармер", "сунак",
        "италија", "италијански", "рим", "мелони",
        "шпанија", "шпански", "мадрид", "санчез",
        "полска", "полски", "варшава", "туск", "дуда",
        "холандија", "амстердам", "вилдeрс",
        "шведска", "шведски", "стокхолм",
        "норвешка", "осло",
        "данска", "копенхаген",
        "финска", "хелсинки",
        "австрија", "австриски", "виена", "беч", "нехамер",
        "португалија", "лисабон",
        "чешка", "прага", "фиала",
        "унгарија", "будимпешта", "орбан",
        "романија", "букурешт",
        "швајцарија", "женева", "берн",
        "еврозона", "шенген", "европски совет", "европски суд",
        "european union", "european commission", "brussels", "euro",
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
        "inflation", "tariffs", "market", "markets", "economy", "budget", "finance",
    ]),
    ("Здравје", [
        "здравје", "медицина", "болест", "вирус", "пандемија", "вакцина", "ковид",
        "лекари", "болница", "клиника", "терапија", "здравствен", "лекови",
        "симптоми", "дијагноза", "исхрана", "витамини", "фитнес", "ментално",
        "операција", "пациент", "пациенти", "аптека", "рецепт",
        "hospital", "virus", "vaccine", "health",
    ]),
    ("Забава", [
        "забава", "музика", "филм", "кино", "холивуд", "актер", "актерка",
        "пејач", "пејачка", "концерт", "албум", "сцена", "култура", "уметност",
        "театар", "изложба", "мода", "стил", "ѕвезда", "славни", "шоу", "евровизија",
        "оскар", "греми", "фестивал", "премиера", "ревија",
        "movie", "music", "film", "show", "celebrity",
    ]),
    ("Криминал", [
        "криминал", "убиство", "кражба", "напад", "полиција", "мвр", "апсење",
        "уапсен", "уапсени", "притвор", "суд", "судење", "пресуда", "затвор",
        "дрога", "оружје", "инцидент", "престрелка", "крв", "тепачка",
        "обвинителство", "обвинет", "осомничен", "измама", "корупција",
        "crime", "murder", "police", "arrest",
    ]),
    ("Живот", [
        "живот", "стил", "храна", "патување", "туризам", "одмор", "семејство",
        "деца", "образование", "училиште", "факултет", "студенти", "наука",
        "време", "прогноза", "сонце", "дожд", "снег", "автомобили", "возила",
        "сообраќај", "несреќа", "патни", "превоз", "животни", "природа",
        "lifestyle", "travel", "family", "education",
    ]),
    ("Политика", [
        "политика", "влада", "министер", "претседател", "парламент", "собрание",
        "избори", "гласање", "партија", "сдсм", "вмро-дпмне", "дуи", "левица", "знам",
        "закон", "реформа", "дипломатија", "амбасадор", "протест", "дебата",
        "самит", "договор", "лидер", "политички", "државен", "функционер",
        "мицкоски", "сиљановска", "ахмети", "филипче", "апасиев",
        "government", "president", "parliament", "minister", "election", "summit",
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
    if best_topic and best_score >= 1.0:
        return best_topic
    return "Вести"


def detect_country(source_name: str) -> str:
    """Return the ISO country code for a given source name. Defaults to MK."""
    return _COUNTRY_MAP.get(source_name, "MK")


def normalize_headline(title: str) -> str:
    """Clean up news titles by stripping tags, extra whitespace and common prefixes."""
    if not title: return ""
    # Decode HTML entities
    title = html.unescape(title)
    # Strip HTML tags
    t = re.sub(r'<[^>]+>', '', title)
    # Strip common prefixes and sensationalist labels
    prefixes = [
        "ВИДЕО", "ФОТО", "ГАЛЕРИЈА", "БРЕЈКИНГ", "ЕКСКЛУЗИВНО", "ПОТВРДЕНО", 
        "СКАНДАЛ", "УЖАС", "ТРАГЕДИЈА", "ВО ЖИВО", "ИНТЕРВЈУ", "АНАЛИЗА",
        "СТРАВИЧНО", "ШОКАНТНО", "НЕВЕРОЈАТНО", "ПОВРЗАНО", "ГЛЕДАЈТЕ",
        "BREAKING", "EXCLUSIVE", "LIVE", "VIDEO", "PHOTO", "GALLERY"
    ]
    pattern = r'^(' + '|'.join(prefixes) + r')[:\s\-–—]+'
    t = re.sub(pattern, '', t, flags=re.IGNORECASE)
    
    # Standardize whitespace
    t = " ".join(t.split())
    return t.strip()
