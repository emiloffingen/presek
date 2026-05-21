"""
categories.py — Article categorization for Presek
Allowed categories (exactly 6, geographic):
  Srbija = domestic news, default fallback
  Balkan     = Serbia, Kosovo, Albania, Greece, Bulgaria, Montenegro,
               Bosnia, Croatia, Turkey
  Evropa     = EU / European news (excluding Germany)
  Germanija  = Germany standalone
  Amerika    = USA + Canada
  Svet       = everything else (Australia, Asia, Africa, Middle East, etc.)
"""

import html
import re

_CYR_TO_LAT_MAP = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "ђ": "dj",
    "е": "e",
    "ж": "zh",
    "з": "z",
    "ѕ": "dz",
    "и": "i",
    "ј": "j",
    "к": "k",
    "л": "l",
    "љ": "lj",
    "м": "m",
    "н": "n",
    "њ": "nj",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "ћ": "c",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "џ": "dzh",
    "ш": "sh",
    "ѓ": "gj",
    "ќ": "kj",
    "я": "ja",
    "ю": "ju",
    "щ": "sht",
    "ъ": "a",
}


def _transliterate_to_latin(text: str) -> str:
    """Simple transliteration for keyword matching."""
    if not text:
        return ""
    res = []
    for char in text.lower():
        res.append(_CYR_TO_LAT_MAP.get(char, char))
    return "".join(res)


ALLOWED_CATEGORIES = {
    "Srbija",
    "Makedonija",
    "Balkan",
    "Evropa",
    "Germanija",
    "Amerika",
    "Svet",
}

THEMATIC_TOPICS = {
    "Politika",
    "Ekonomija",
    "Tehnologija",
    "Sport",
    "Zabava",
    "Kultura",
    "Zdravje",
    "vesti",
    "Kriminal",
    "Zivot",
}


def _keyword_matches(text: str, keyword: str) -> bool:
    keyword = str(keyword or "").strip().lower()
    if not keyword:
        return False
    # Use word boundaries that support Cyrillic
    pattern = r"(?<![A-Za-z\w])" + re.escape(keyword) + r"(?![A-Za-z\w])"
    return bool(re.search(pattern, text))


def _score_keyword_group(text: str, keywords: list[str], topic_name: str = "") -> float:
    score = 0.0
    for kw in sorted(keywords, key=len, reverse=True):
        if not _keyword_matches(text, kw):
            continue
        if " " in kw:
            score += 2.5
        elif len(kw) >= 7:
            score += 1.5
        else:
            score += 1.0

    # Boost economy specifically if keywords are found
    if topic_name == "Ekonomija" and any(k in text for k in ["budzet", "inflacija", "Ekonomija", "finansii"]):
        score += 1.0

    return score


def validate_category(category: str, default: str = "Srbija") -> str:
    """Return category if it is in the allowed list, else default."""
    return category if category in ALLOWED_CATEGORIES else default


# ORDER MATTERS — first match wins.
CATEGORIES = [
    (
        "Germanija",
        [
            "germanija",
            "germanski",
            "germanska",
            "germanskiot",
            "berlin",
            "hamburg",
            "minhen",
            "frankfurt",
            "koln",
            "stutgart",
            "bundestag",
            "bundesrat",
            "bundesver",
            "solc",
            "merc",
            "merkel",
            "baern",
            "dortmund",
            "germany",
            "berlin",
            "scholz",
        ],
    ),
    (
        "Makedonija",
        [
            "makedonija",
            "makedonski",
            "makedonska",
            "skopje",
            "bitola",
            "ohrid",
            "tetovo",
            "kumanovo",
            "mickoski",
            "siljanovska",
            "filipce",
            "kovacevski",
            "taravari",
            "kasami",
            "apasiev",
            "ahmeti",
            "grubi",
            "bujar osmani",
            "macedonia",
            "sobranie",
            "vlada na rm",
        ],
    ),
    (
        "Srbija",
        [
            "srbija",
            "srpski",
            "srpska",
            "beograd",
            "vucic",
            "dacic",
            "brnabic",
            "nis",
            "novi sad",
            "vulin",
            "gasic",
            "vesic",
            "djilas",
            "marinika",
            "aleksic",
            "savo manojlovic",
            "serbia",
            "belgrade",
            "skupstina srbije",
        ],
    ),
    (
        "Balkan",
        [
            "bugarija",
            "bugarski",
            "sofija",
            "radev",
            "glavcev",
            "borisov",
            "petkov",
            "grcija",
            "grcki",
            "atina",
            "micotakis",
            "kaselakis",
            "cipras",
            "albanija",
            "tirana",
            "rama",
            "berisa",
            "meta",
            "kosovo",
            "pristina",
            "kurti",
            "osmani",
            "konjufca",
            "hrvatska",
            "zagreb",
            "milanovic",
            "plenkovic",
            "bosna",
            "bih",
            "saraevo",
            "dodik",
            "becirovic",
            "komsic",
            "crna gora",
            "podgorica",
            "spajic",
            "milatovic",
            "abazovic",
            "slovenija",
            "ljubljana",
            "golob",
            "turcija",
            "turski",
            "ankara",
            "erdogan",
            "istanbul",
            "fidan",
            "Balkan",
            "balkanski",
            "bulgaria",
            "greece",
            "albania",
            "kosovo",
            "croatia",
            "turkey",
            "slovenia",
        ],
    ),
    (
        "Amerika",
        [
            "soedineti amerikanski drzavi",
            "sad",
            "amerikanski",
            "amerika",
            "vasington",
            "belata kuca",
            "kongres na sad",
            "kapitol",
            "tramp",
            "haris",
            "bajden",
            "pentagon",
            "stejt department",
            "volstrit",
            "silikonska dolina",
            "fbr",
            "cia",
            "kanada",
            "kanadski",
            "otava",
            "toronto",
            "trido",
            "nba",
            "mls",
            "lejkers",
            "hjuston",
            "majami hit",
            "golden stajt",
            "los andzeles",
            "inter majami",
            "united states",
            "washington",
            "white house",
            "congress",
            "trump",
            "biden",
            "nba",
            "mls",
            "lakers",
            "houston",
            "inter miami",
        ],
    ),
    (
        "Evropa",
        [
            "evropska unija",
            "evroparlament",
            "evropska komisija",
            "brisel",
            "strazbur",
            "fon der lajen",
            "borel",
            "mecola",
            "francija",
            "francuski",
            "pariz",
            "makron",
            "le pen",
            "atal",
            "velika britanija",
            "britanski",
            "london",
            "obedineto kralstvo",
            "starmer",
            "sunak",
            "italija",
            "italijanski",
            "rim",
            "meloni",
            "salvini",
            "spanija",
            "spanski",
            "madrid",
            "sancez",
            "feiho",
            "polska",
            "polski",
            "varsava",
            "tusk",
            "duda",
            "holandija",
            "amsterdam",
            "vilders",
            "rute",
            "belgija",
            "portugalija",
            "ceska",
            "ungarija",
            "avstrija",
            "svedska",
            "norveska",
            "danska",
            "finska",
            "evrozona",
            "sengen",
            "evropski sovet",
            "evropski sud",
            "celzi",
            "arsenal",
            "liverpul",
            "mancester junajted",
            "mancester siti",
            "totenhem",
            "psz",
            "pari sen zermen",
            "real madrid",
            "barselona",
            "atletiko",
            "juventus",
            "milan",
            "inter",
            "napoli",
            "roma",
            "benfika",
            "porto",
            "sporting",
            "ajaks",
            "psv",
            "european union",
            "european commission",
            "brussels",
            "euro",
            "chelsea",
            "arsenal",
            "liverpool",
            "manchester united",
            "manchester city",
            "tottenham",
            "psg",
            "paris saint-germain",
            "real madrid",
            "barcelona",
            "atletico",
            "juventus",
            "milan",
            "inter",
            "napoli",
            "roma",
        ],
    ),
    (
        "Svet",
        [
            "rusija",
            "ruski",
            "moskva",
            "putin",
            "kremlj",
            "lavrov",
            "medvedev",
            "ukraina",
            "ukrainski",
            "kiev",
            "zelenski",
            "kuleba",
            "kina",
            "kineski",
            "peking",
            "si dzinping",
            "japonija",
            "japonski",
            "tokio",
            "indija",
            "indiski",
            "nju delhi",
            "modi",
            "izrael",
            "izraelski",
            "tel aviv",
            "netanjahu",
            "palestina",
            "gaza",
            "hamas",
            "rafa",
            "iran",
            "iranski",
            "teheran",
            "hamenei",
            "sirija",
            "damask",
            "irak",
            "avganistan",
            "talibanci",
            "severna koreja",
            "pjongjang",
            "kim dzong un",
            "bliskiot istok",
            "bliski istok",
            "afrika",
            "afrikanski",
            "egipet",
            "kairo",
            "avstralija",
            "avstraliski",
            "brazil",
            "meksiko",
            "argentina",
            "oon",
            "svetska zdravstvena organizacija",
            "szo",
            "unmik",
            "kfor",
            "svetski",
            "svetska",
            "nato",
            "stoltenberg",
            "g7",
            "g20",
            "briks",
            "terorizam",
            "sankcii",
            "migranti",
            "begalci",
            "voena operacija",
            "voeni sili",
            "vojna",
            "raketen napad",
            "raketi",
            "bombardiranje",
            "middle east",
            "united nations",
            "nato",
            "russia",
            "ukraine",
        ],
    ),
]

TITLE_PROPER_NOUNS = [
    (re.compile(r"\bsrpskata opozicija\b", re.IGNORECASE), "Srpskata opozicija"),
    (re.compile(r"\biran\b", re.IGNORECASE), "Iran"),
    (re.compile(r"\bdanska\b", re.IGNORECASE), "Danska"),
    (re.compile(r"\bevropa\b", re.IGNORECASE), "Evropa"),
    (re.compile(r"\bjugoslavija\b", re.IGNORECASE), "Jugoslavija"),
    (re.compile(r"\bsrbija\b", re.IGNORECASE), "Srbija"),
    (re.compile(r"\bbugarija\b", re.IGNORECASE), "Bugarija"),
    (re.compile(r"\bsrbija\b", re.IGNORECASE), "Srbija"),
    (re.compile(r"\bgrcija\b", re.IGNORECASE), "Grcija"),
    (re.compile(r"\balbanija\b", re.IGNORECASE), "Albanija"),
    (re.compile(r"\bkosovo\b", re.IGNORECASE), "Kosovo"),
    (re.compile(r"\brusija\b", re.IGNORECASE), "Rusija"),
    (re.compile(r"\bukraina\b", re.IGNORECASE), "Ukraina"),
    (re.compile(r"\bizrael\b", re.IGNORECASE), "Izrael"),
    (re.compile(r"\bpalestina\b", re.IGNORECASE), "Palestina"),
    (re.compile(r"\bgermanija\b", re.IGNORECASE), "Germanija"),
    (re.compile(r"\bfrancija\b", re.IGNORECASE), "Francija"),
    (re.compile(r"\bbritanija\b", re.IGNORECASE), "Britanija"),
    (re.compile(r"\bkina\b", re.IGNORECASE), "Kina"),
    (re.compile(r"\bpeking\b", re.IGNORECASE), "Peking"),
    (re.compile(r"\bsad\b", re.IGNORECASE), "SAD"),
    (re.compile(r"\beu\b", re.IGNORECASE), "EU"),
    (re.compile(r"\bnato\b", re.IGNORECASE), "NATO"),
    (re.compile(r"\bskopje\b", re.IGNORECASE), "Skopje"),
    (re.compile(r"\bbitola\b", re.IGNORECASE), "Bitola"),
    (re.compile(r"\bohrid\b", re.IGNORECASE), "Ohrid"),
    (re.compile(r"\btetovo\b", re.IGNORECASE), "Tetovo"),
    (re.compile(r"\bkumanovo\b", re.IGNORECASE), "Kumanovo"),
    (re.compile(r"\bprilep\b", re.IGNORECASE), "Prilep"),
    (re.compile(r"\bveles\b", re.IGNORECASE), "Veles"),
    (re.compile(r"\bstip\b", re.IGNORECASE), "Stip"),
    (re.compile(r"\bstrumica\b", re.IGNORECASE), "Strumica"),
    (re.compile(r"\bgostivar\b", re.IGNORECASE), "Gostivar"),
    (re.compile(r"\bkavadarci\b", re.IGNORECASE), "Kavadarci"),
    (re.compile(r"\bkocani\b", re.IGNORECASE), "Kocani"),
    (re.compile(r"\bkicevo\b", re.IGNORECASE), "Kicevo"),
    (re.compile(r"\bstruga\b", re.IGNORECASE), "Struga"),
    (re.compile(r"\bgevgelija\b", re.IGNORECASE), "Gevgelija"),
    (re.compile(r"\bkriva palanka\b", re.IGNORECASE), "Kriva Palanka"),
    (re.compile(r"\bmickoski\b", re.IGNORECASE), "Mickoski"),
    (re.compile(r"\bsiljanovska\b", re.IGNORECASE), "Siljanovska"),
    (re.compile(r"\bfilipce\b", re.IGNORECASE), "Filipce"),
    (re.compile(r"\bapasiev\b", re.IGNORECASE), "Apasiev"),
    (re.compile(r"\bahmeti\b", re.IGNORECASE), "Ahmeti"),
    (re.compile(r"\bkasami\b", re.IGNORECASE), "Kasami"),
    (re.compile(r"\btaravari\b", re.IGNORECASE), "Taravari"),
    (re.compile(r"\bgasi\b", re.IGNORECASE), "Gasi"),
    (re.compile(r"\bmedziti\b", re.IGNORECASE), "Medziti"),
    (re.compile(r"\bbasanovic\b", re.IGNORECASE), "Basanovic"),
    (re.compile(r"\bzaev\b", re.IGNORECASE), "Zaev"),
    (re.compile(r"\btito\b", re.IGNORECASE), "Tito"),
    (re.compile(r"\bvlada\b", re.IGNORECASE), "Vlada"),
    (re.compile(r"\bsobranie\b", re.IGNORECASE), "Sobranie"),
    (re.compile(r"\bsdsm\b", re.IGNORECASE), "SDSM"),
    (re.compile(r"\bvmro-dpmne\b", re.IGNORECASE), "VMRO-DPMNE"),
    (re.compile(r"\bdui\b", re.IGNORECASE), "DUI"),
    (re.compile(r"\blevica\b", re.IGNORECASE), "Levica"),
    (re.compile(r"\bznam\b", re.IGNORECASE), "ZNAM"),
    (re.compile(r"\bmvr\b", re.IGNORECASE), "MVR"),
    (re.compile(r"\bmnr\b", re.IGNORECASE), "MNR"),
    (re.compile(r"\bmo\b", re.IGNORECASE), "MO"),
    (re.compile(r"\bmz\b", re.IGNORECASE), "MZ"),
    (re.compile(r"\bujp\b", re.IGNORECASE), "UJP"),
    (re.compile(r"\bbg\b", re.IGNORECASE), "BG"),
]


def detect_category(
    title: str,
    description: str = "",
    source: str = "",
    forced_category: str = None,
    lang: str = "sr",
) -> str:
    """Return category for an article."""
    if forced_category and forced_category in ALLOWED_CATEGORIES:
        return forced_category

    raw_text = (title + " " + description).lower()
    text = _transliterate_to_latin(raw_text)
    best_category = None
    best_score = 0.0
    for cat_name, keywords in CATEGORIES:
        score = _score_keyword_group(text, keywords)
        if score > best_score:
            best_category = cat_name
            best_score = score

    if best_category and best_score >= 1.0:
        return best_category

    return "Makedonija" if lang == "mk" else "Srbija"


# ── Sub-categories (regional) ──────────────────────────────────────
SUB_CATEGORIES = [
    (
        "Beograd",
        [
            "Beograd",
            "grad Beograd",
            "aerodrom Beograd",
            "pobednik",
            "kalemegdan",
            "vracar",
            "stari grad",
            "savski venac",
            "palilula",
            "zvezdara",
            "vozdovac",
            "cukarica",
            "rakovica",
            "novi beograd",
            "zemun",
            "obrenovac",
            "lazarevac",
            "mladenovac",
            "grocka",
            "barajevo",
            "sopot",
            "surcin",
            "belgrade",
        ],
    ),
    (
        "Novi Sad",
        [
            "Novi Sad",
            "Novom Sadu",
            "Novog Sada",
            "Novosadski",
            "grad Novi Sad",
            "vojvodina",
            "liman",
            "strand",
            "petrovaradin",
            "spens",
            "detelinara",
            "telep",
            "sremska kamenica",
            "fruska gora",
        ],
    ),
    (
        "Nis",
        [
            "Nis",
            "Nisu",
            "Nisa",
            "niski",
            "grad Nis",
            "niska banja",
            "mediana",
            "pantelej",
            "crveni krst",
            "palilula nis",
            "konstantin veliki",
        ],
    ),
    (
        "Skopje",
        [
            "Skopje",
            "skopski",
            "gradonacalnik",
            "arsovska",
            "karpos",
            "centar",
            "gazi baba",
            "aerodrom",
            "cair",
            "butel",
            "kisela voda",
            "djorce petrov",
            "djorce",
            "suto orizari",
            "saraj",
            "aracinovo",
            "volkovo",
            "dracevo",
            "lisice",
            "avtokomanda",
            "zelezara",
            "madzari",
            "pintija",
            "sopiste",
            "petrovec",
            "ilinden",
            "zlostrub",
        ],
    ),
    (
        "Republika",
        [
            "bitola",
            "ohrid",
            "prilep",
            "kumanovo",
            "tetovo",
            "stip",
            "veles",
            "kavadarci",
            "gevgelija",
            "strumica",
            "kocani",
            "berovo",
            "delcevo",
            "kriva palanka",
            "gostivar",
            "debar",
            "kicevo",
            "struga",
            "sveti nikole",
            "negotino",
            "radovis",
            "vinica",
            "makedonska kamenica",
            "demir hisar",
            "resen",
            "probistip",
            "krusevo",
            "valandovo",
            "kratovo",
            "demir kapija",
            "pehcevo",
            "dojran",
            "mavrovo",
            "valandovo",
            "bogdanci",
            "makpetrol",
        ],
    ),
]


def detect_subcategory(title: str, description: str = "", country: str = "RS") -> str | None:
    """Detect optional sub-category (regional). Returns None if no match."""
    raw_text = (title + " " + description).lower()
    text = _transliterate_to_latin(raw_text)

    # Filter subcategories by country to avoid cross-border misclassification
    # (e.g., 'gradonacalnik' is common to both but usually refers to the capital)
    allowed = ["Republika", "Skopje"] if country == "MK" else ["Beograd", "Novi Sad", "Nis"]

    for sub_name, keywords in SUB_CATEGORIES:
        if sub_name not in allowed:
            continue
        if any(_keyword_matches(text, kw) for kw in keywords):
            return sub_name
    return None


# ── Source country code map ────────────────────────────────────────
_COUNTRY_MAP: dict[str, str] = {
    "N1 Info": "RS",
    "Kurir.rs": "RS",
    "danas.rs": "RS",
    "Dnevnik.bg": "BG",
    "24 Chasa BG": "BG",
    "Capital.bg": "BG",
    "Index.hr": "HR",
    "Jutarnji": "HR",
    "Klix.ba": "BA",
    "Vijesti.me": "ME",
    "RTCG": "ME",
    "Telegrafi KS": "XK",
    "Daily Sabah": "TR",
    "Anadolu Agency": "TR",
    "Balkan Insight": "Balkan",
    "Tagesschau": "DE",
    "CNN": "US",
    "BBC News": "GB",
    "Reuters": "GB",
}


# ── Thematic Topic Detection ──────────────────────────────────────

TOPICS = [
    (
        "Politika",
        [
            "Politika",
            "vlada",
            "vladata",
            "minister",
            "pretsedatel",
            "parlament",
            "parlamentot",
            "sobranie",
            "sobranieto",
            "izbori",
            "glasanje",
            "partija",
            "sdsm",
            "vmro-dpmne",
            "dui",
            "levica",
            "zakon",
            "reforma",
            "diplomatija",
            "ambasador",
            "protest",
            "protesti",
            "debata",
            "samit",
            "dogovor",
            "lider",
            "politicki",
            "drzaven",
            "funkcioner",
            "mickoski",
            "hristijan mickoski",
            "siljanovska",
            "davkova",
            "ahmeti",
            "filipce",
            "apasiev",
            "tramp",
            "donald tramp",
            "premier",
            "ministerstvo",
            "ministerstvoto",
            "institucii",
            "drzavna",
            "government",
            "president",
            "parliament",
            "minister",
            "election",
            "summit",
            "politics",
        ],
    ),
    (
        "Ekonomija",
        [
            "Ekonomija",
            "finansii",
            "budzet",
            "inflacija",
            "kamatna stapka",
            "kamati",
            "berza",
            "akcii",
            "investicii",
            "banka",
            "bruto domasen proizvod",
            "bdp",
            "danok",
            "plata",
            "minimalna plata",
            "penzija",
            "pazar",
            "ceni",
            "nafta",
            "energija",
            "gas",
            "kriza",
            "biznis",
            "kompanija",
            "korporacija",
            "trgovija",
            "uvoz",
            "izvoz",
            "firmi",
            "firmite",
            "pretprijatija",
            "inflation",
            "tariffs",
            "market",
            "markets",
            "economy",
            "budget",
            "finance",
            "gdp",
        ],
    ),
    (
        "Sport",
        [
            "fudbal",
            "kosarka",
            "rakomet",
            "teniser",
            "teniserka",
            "atletika",
            "liga na sampioni",
            "premier liga",
            "fifa",
            "uefa",
            "olimpiski",
            "olimpijada",
            "svetsko prvenstvo",
            "mundijal 2026",
            "evropsko prvenstvo",
            "natprevar",
            "prvenstvo",
            "kup",
            "rezultati",
            "transfer",
            "gol",
            "trener",
            "selektor",
            "reprezentacija",
            "grend slem",
            "nokaut",
            "finale",
            "polufinale",
            "kosarkar",
            "fudbaler",
            "rakometar",
            "boks",
            "formula 1",
            "f1",
            "moto gp",
            "vardar",
            "pelister",
            "skupi",
            "janik siner",
            "alkaraz",
            "djokovic",
            "jokic",
            "doncic",
            "vinisius",
            "mbape",
            "football",
            "basketball",
            "tennis",
            "champions league",
            "nba",
        ],
    ),
    (
        "Tehnologija",
        [
            "Tehnologija",
            "pameten telefon",
            "smartfon",
            "aplikacija",
            "softver",
            "hardver",
            "internet",
            "sajber",
            "haker",
            "kriptovaluti",
            "bitkoin",
            "blokcein",
            "vselena",
            "raketa",
            "nasa",
            "ilon mask",
            "inovacija",
            "robot",
            "cip",
            "procesor",
            "majkrosoft",
            "gugl",
            "epl",
            "samsung",
            "fejsbuk",
            "meta",
            "tviter",
            "h",
            "socijalni mrezi",
            "gejming",
            "konzola",
            "plejstejsn",
            "software",
            "hardware",
            "ai",
            "artificial intelligence",
            "iphone",
            "android",
        ],
    ),
    (
        "Zdravje",
        [
            "zdravje",
            "medicina",
            "bolest",
            "virus",
            "pandemija",
            "vakcina",
            "kovid",
            "lekari",
            "bolnica",
            "klinika",
            "terapija",
            "zdravstven",
            "lekovi",
            "simptomi",
            "dijagnoza",
            "ishrana",
            "vitamini",
            "fitnes",
            "mentalno",
            "operacija",
            "pacient",
            "pacienti",
            "apteka",
            "hospital",
            "virus",
            "vaccine",
            "health",
            "medical",
        ],
    ),
    (
        "Kultura",
        [
            "Kultura",
            "umetnost",
            "teatar",
            "izlozba",
            "knizevnost",
            "literatura",
            "pisatel",
            "pisatelka",
            "kniga",
            "biblioteka",
            "muzej",
            "galerija",
            "spektakl",
            "festival",
            "kulturen",
            "kulturna",
            "umetnik",
            "umetnica",
            "kino",
            "film",
            "kinoteka",
            "premiera",
            "arhitektura",
            "dizajn",
            "culture",
            "art",
            "museum",
            "theater",
            "literature",
        ],
    ),
    (
        "Zabava",
        [
            "zabava",
            "muzika",
            "holivud",
            "akter",
            "akterka",
            "pejac",
            "pejacka",
            "koncert",
            "album",
            "scena",
            "moda",
            "zvezda",
            "slavni",
            "sou",
            "evrovizija",
            "oskar",
            "gremi",
            "revija",
            "poznati",
            "trac",
            "dzet-set",
            "movie",
            "music",
            "film",
            "show",
            "celebrity",
            "entertainment",
        ],
    ),
    (
        "Kriminal",
        [
            "kriminal",
            "ubistvo",
            "krazba",
            "napad",
            "policija",
            "mvr",
            "apsenje",
            "uapsen",
            "uapseni",
            "pritvor",
            "sudenje",
            "presuda",
            "zatvor",
            "droga",
            "oruzje",
            "prestrelka",
            "tepacka",
            "obvinitelstvo",
            "obvinet",
            "osomnicen",
            "izmama",
            "korupcija",
            "crime",
            "murder",
            "police",
            "arrest",
            "investigation",
        ],
    ),
    (
        "Zivot",
        [
            "hrana",
            "patuvanje",
            "turizam",
            "odmor",
            "semejstvo",
            "deca",
            "Obrazovanje",
            "uciliste",
            "fakultet",
            "studenti",
            "nauka",
            "vreme",
            "prognoza",
            "sonce",
            "dozd",
            "sneg",
            "avtomobili",
            "vozila",
            "soobracaj",
            "nesreca",
            "patni",
            "prevoz",
            "zivotni",
            "priroda",
            "lifestyle",
            "travel",
            "family",
            "education",
            "weather",
        ],
    ),
]


import logging

logger = logging.getLogger(__name__)


def detect_topic(title: str, description: str = "") -> str:
    """Detect thematic topic (Sport, Tech, Economy, etc.). Defaults to 'vesti'."""
    raw_text = (title + " " + description).lower()
    text = _transliterate_to_latin(raw_text)
    best_topic = None
    best_score = 0.0
    for topic_name, keywords in TOPICS:
        score = _score_keyword_group(text, keywords, topic_name=topic_name)
        if score > best_score:
            best_topic = topic_name
            best_score = score

    result = best_topic if (best_topic and best_score >= 1.5) else "vesti"
    logger.debug(f"Categorizing article: title='{title}', detected_topic='{result}', score={best_score}")
    return result


def detect_country(source_name: str) -> str:
    """Return the ISO country code for a given source name. Defaults to RS."""
    return _COUNTRY_MAP.get(source_name, "RS")


def normalize_headline(title: str) -> str:
    """Clean up and professionalize news titles for a high-end editorial feel."""
    if not title:
        return ""

    # 1. Preliminary Cleaning
    t = html.unescape(title)
    t = re.sub(r"<[^>]+>", "", t)  # Strip HTML

    # 2. Aggressive Tag & Decorative Prefix Removal
    tags_pattern = r"(\[[^\]]*(VIDEO|FOTO|GALERIJA|BRIFING|VIDEO|PHOTO|GALLERY|LIVE)[^\]]*\]|\([^\)]*(VIDEO|FOTO|GALERIJA|BRIFING|VIDEO|PHOTO|GALLERY|LIVE)[^\)]*\))"
    t = re.sub(tags_pattern, "", t, flags=re.IGNORECASE)

    # Common prefix labels (standing alone or followed by colon/dash)
    sensationalist = [
        "VIDEO",
        "FOTO",
        "GALERIJA",
        "VIDEO",
        "PHOTO",
        "GALLERY",
        "BRIFING",
        "UZIVO",
        "NOVO",
        "ITNO",
        "VNIMANIE",
        "LIVE",
        "BREJKING",
        "EKSKLUZIVNO",
        "potvrdeno",
        "SKANDAL",
        "UZAS",
        "TRAGEDIJA",
        "INTERVJU",
        "ANALIZA",
        "STRAVICNO",
        "SOKANTNO",
        "NEVEROJATNO",
        "GLEDAJTE",
        "VECER",
        "MAKFAKS",
        "FOKUS",
        "DENESEN",
        "KURIR",
        "REPUBLIKA",
        "BREAKING",
        "EXCLUSIVE",
        "OTKRIVAME",
        "VOZNEMIRUVACKO",
        "VIDEOINTERVJU",
        "VIDEO-INTERVJU",
    ]
    prefix_pattern = r"^(" + "|".join(sensationalist) + r")[\s\|:–—-]+"
    t = re.sub(prefix_pattern, "", t, count=1, flags=re.IGNORECASE)

    # Strip any remaining prefix followed by colon (e.g. "Beograd: ...", "Manasievski: ...")
    t = re.sub(r"^[A-ZА-Яa-zа-я\s\-]{3,}:", "", t).strip()

    # 3. Suffix / Source Attribution Cleanup
    sources = [
        "360 stepeni",
        "Sloboden pecat",
        "Makfaks",
        "Fokus",
        "Kanal 5",
        "Sitel",
        "Telma",
        "MRT",
        "A1on",
        "Lokalno",
        "Lokalno",
        "Vecer",
        "Vecer",
        "Nezavisen",
        "Nezavisen",
        "Republika",
        "Republika",
        "Kurir",
        "Kurir",
        "Denesen",
        "Denesen",
        "Meta.mk",
        "META",
        "Plusinfo",
        "Plusinfo",
        "Sakam da kazam",
        "SDK",
        "SDK.mk",
        "Deutsche Welle",
        "DW",
        "DW.com",
        "Radio Slobodna Evropa",
        "RSE",
        "RSE",
        "nova Srbija",
        "Brifing",
    ]
    suffix_pattern = r"[\s\|:–—-]+(" + "|".join(sources) + r")$"
    t = re.sub(suffix_pattern, "", t, flags=re.IGNORECASE)

    # 4. De-Shouting (Sentence Case)
    # Improved check: if more than 65% of alpha chars are uppercase
    # OR if title starts with a long uppercase segment before a colon
    alpha_chars = [c for c in t if c.isalpha()]
    upper_count = sum(1 for c in alpha_chars if c.isupper())
    alpha_count = len(alpha_chars)

    # Prefix check like "Srbija: Naslov..."
    long_upper_prefix = re.match(r"^([A-ZА-Я\s]{6,}):", t)

    if (alpha_count >= 6 and (upper_count / alpha_count) > 0.65) or long_upper_prefix:
        # Before lower-casing, protect common Serbian/International acronyms
        acronyms = {
            "EU",
            "NATO",
            "SAD",
            "MVR",
            "SZO",
            "SNS",
            "DS",
            "UJP",
            "OJO",
            "VMRO",
            "ЕУ",
            "НАТО",
            "САД",
            "МВР",
            "СЗО",
            "СНС",
            "ДС",
            "УЈП",
            "ОЈО",
            "ВМРО",
        }

        # Lowercase and capitalize only first letter
        t_normalized = t.lower()
        t_normalized = t_normalized[0].upper() + t_normalized[1:]

        # Restore acronyms
        for acronym in acronyms:
            t_normalized = re.sub(rf"\b{re.escape(acronym)}\b", acronym, t_normalized, flags=re.IGNORECASE)
        t = t_normalized

    # 5. Serbian Quote Standardization (Standard quotes „...“)
    t = t.replace("''", '"')
    t = t.replace("”", '"')  # English closing quote -> standard double quote
    t = re.sub(r'(?<!\w)["\']([^"\']+)["\'](?!\w)', r"„\1“", t)

    # 5b. Typographical and Mathematical Normalization
    # Ellipses (three or more dots -> …)
    t = re.sub(r'\.{3,}', '…', t)
    
    # Numeric Ranges (e.g., 10-15 or 10 - 15 -> 10–15)
    t = re.sub(r'(\d+)\s*[-–—]\s*(\d+)', r'\1–\2', t)
    
    # Spaced hyphens/dashes separating clauses -> spaced En-dash ( – )
    t = re.sub(r'\s+[-–—]+\s+', ' – ', t)
    
    # Mathematical Multiplication (e.g., 3x4 or 3*4 -> 3 × 4)
    t = re.sub(r'(\d+)\s*[x*×]\s*(\d+)', r'\1 × \2', t)
    
    # Punctuation spacing: no space before, exactly one space after
    # Strip spaces before punctuation
    t = re.sub(r'\s+([.,;:!?…])', r'\1', t)
    # Add space after punctuation if followed directly by a letter (exclude digits to preserve time formats and decimal numbers)
    t = re.sub(r'([,;:!?…])(?=[A-Za-zА-Яа-я])', r'\1 ', t)
    t = re.sub(r'\.(?=[A-ZА-Я])', r'. ', t)



    # 6. Technical Polish
    # Remove common clickbait fillers
    fillers = [
        "POVRZANO vesti",
        "POVRZANO",
        "PROCITAJTE I",
        "FOTOGALERIJA",
        "GLEDAJTE VO ZIVO",
        "SLEDETE VO ZIVO",
    ]
    for filler in fillers:
        t = re.sub(rf"\b{re.escape(filler)}\b", "", t, flags=re.IGNORECASE)

    t = re.sub(r"[\?\!]{2,}", lambda m: m.group(0)[0], t)  # No !!! or ???
    t = " ".join(t.split())  # Standardize whitespace
    t = t.strip(" -–—:|")  # Remove trailing/leading decorations
    for pattern, replacement in TITLE_PROPER_NOUNS:
        t = pattern.sub(replacement, t)

    if t and t[0].islower():
        t = t[0].upper() + t[1:]

    return t.strip()
