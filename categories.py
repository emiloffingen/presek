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

ALLOWED_CATEGORIES = {
    "Македонија", "Балкан", "Европа", "Германија", "Америка", "Свет",
}


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
        "шолц", "мерц", "меркел",
    ]),

    ("Балкан", [
        "србија", "српски", "белград", "вучиќ",
        "бугарија", "бугарски", "софија",
        "грција", "грчки", "атина",
        "албанија", "тирана", "рама",
        "косово", "приштина", "курти",
        "хрватска", "загреб",
        "босна", "сараево",
        "црна гора", "подгорица",
        "турција", "турски", "анкара", "ердоган", "истанбул",
        "балкан", "балкански",
        "северна македонија и",  # regional framing ("Н. Македонија и Србија")
    ]),

    ("Америка", [
        "соединети американски држави", "сад", "американски",
        "вашингтон", "белата куќа", "конгрес на сад",
        "трамп", "харис", "бајден", "пентагон",
        "волстрит", "силиконска долина",
        "канада", "канадски", "отава", "торонто", "тридо",
    ]),

    # Европа comes after Германија — Germany keywords are already caught above.
    ("Европа", [
        "европска унија", "европарламент", "европска комисија",
        "брисел", "стразбур",
        "франција", "француски", "париз", "макрон",
        "велика британија", "британски", "лондон", "обединето кралство",
        "италија", "италијански", "рим",
        "шпанија", "шпански", "мадрид",
        "полска", "полски", "варшава",
        "холандија", "амстердам",
        "шведска", "шведски", "стокхолм",
        "норвешка", "осло",
        "данска", "копенхаген",
        "финска", "хелсинки",
        "австрија", "австриски", "виена", "беч",
        "португалија", "лисабон",
        "чешка", "прага",
        "унгарија", "будимпешта",
        "романија", "букурешт",
        "швајцарија", "женева", "берн",
        "еврозона", "шенген", "европски совет",
    ]),

    ("Свет", [
        "русија", "руски", "москва", "путин", "кремљ",
        "украина", "украински", "киев", "зеленски",
        "кина", "кинески", "пекинг",
        "јапонија", "јапонски", "токио",
        "индија", "индиски", "њу делхи",
        "израел", "израелски", "тел авив", "палестина", "газа",
        "иран", "ирански", "техеран",
        "сирија", "дамаск", "ирак", "авганистан",
        "блискиот исток", "блиски исток",
        "африка", "африкански",
        "австралија", "австралиски",
        "бразил", "мексико", "аргентина",
        "оон", "светска здравствена организација",
        "светски", "светска",
        "нато",
        "г7", "г20",
        "тероризам", "санкции", "мигранти", "бегалци",
        "воена операција", "воени сили",
        "ракетен напад", "ракети",
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
    for cat_name, keywords in CATEGORIES:
        # Check longer phrases first — more specific phrases win
        for kw in sorted(keywords, key=len, reverse=True):
            # Short single-word keywords need a word-start boundary to avoid
            # false substring matches (e.g. "кина" inside "прекинато").
            if len(kw) <= 4 and " " not in kw:
                if re.search(r"(?<!\w)" + re.escape(kw), text):
                    return cat_name
            elif kw in text:
                return cat_name
    return "Македонија"


# ── Sub-categories (regional) ──────────────────────────────────────
SUB_CATEGORIES = [
    ("Скопје", [
        "скопје", "скопски", "град скопје", "градоначалник",
        "аеродром скопје", "карпош", "центар", "гази баба",
        "чаир", "бутел", "кисела вода", "ѓорче петров",
        "шуто оризари", "сарај", "арачиново",
    ]),
    ("Република", [
        "битола", "охрид", "прилеп", "куманово", "тетово",
        "штип", "велес", "кавадарци", "гевгелија", "струмица",
        "кочани", "берово", "делчево", "крива паланка",
        "гостивар", "дебар", "кичево", "струга",
        "свети николе", "неготино", "радовиш", "виница",
        "македонска каменица", "демир хисар", "ресен",
        "пробиштип", "крушево", "валандово",
    ]),
]


def detect_subcategory(title: str, description: str = "") -> str | None:
    """Detect optional sub-category (regional). Returns None if no match."""
    text = (title + " " + description).lower()
    for sub_name, keywords in SUB_CATEGORIES:
        if any(kw in text for kw in keywords):
            return sub_name
    return None


# ── Source country flag map ────────────────────────────────────────
_COUNTRY_MAP: dict[str, str] = {
    "Tagesschau":    "🇩🇪",
    "Der Spiegel":   "🇩🇪",
    "Bild":          "🇩🇪",
    "SRF News":      "🇨🇭",
    "20 Minuten":    "🇨🇭",
    "CNN":           "🇺🇸",
    "Reuters":       "🇬🇧",
    "NPR":           "🇺🇸",
    "CBC News":      "🇨🇦",
    "CTV News":      "🇨🇦",
    "ABC Australia": "🇦🇺",
    "ANSA":          "🇮🇹",
    "BBC News":      "🇬🇧",
    "The Guardian":  "🇬🇧",
    "N1 Info":       "🇷🇸",
    "B92":           "🇷🇸",
    "Novinite":      "🇧🇬",
    "Kathimerini":   "🇬🇷",
    "Exit News":     "🇦🇱",
    "Top Channel":   "🇦🇱",
    "Klan News":     "🇽🇰",
    "Telegrafi":     "🇽🇰",
    "Daily Sabah":   "🇹🇷",
    "TRT World":     "🇹🇷",
    "Balkan Insight": "🌍",
    "Kurir.rs":      "🇷🇸",
    "Blic.rs":       "🇷🇸",
    "Index.hr":      "🇭🇷",
    "Jutarnji":      "🇭🇷",
    "Klix.ba":       "🇧🇦",
    "Vijesti.me":    "🇲🇪",
}


def detect_country(source_name: str) -> str:
    """Return the country flag emoji for a given source name. Defaults to 🇲🇰."""
    return _COUNTRY_MAP.get(source_name, "🇲🇰")
