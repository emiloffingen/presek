import os
import sys

REQUIRED_RUNTIME_ENV_KEYS = ("DATABASE_URL", "SECRET_KEY")


def validate_required_env(required_keys=REQUIRED_RUNTIME_ENV_KEYS):
    """Validate that critical environment variables are set before serving traffic."""
    missing = [k for k in required_keys if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "presek-mk-vesti")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# ── Additional AI Providers (OpenAI-compatible) ──────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
CEREBRAS_API_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODEL = "llama3.1-8b"

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small-latest"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/auto"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

REFRESH_INTERVAL = 300
FEED_LIMIT = 10
AI_DAILY_LIMIT = 1000000 # Unlimited (paid Gemini fallback tier)
CLUSTER_LOOKBACK = 500  # increased from 200 — handles 36 sources × 10 entries per refresh
BREAKING_SCORE_THRESHOLD = 3.0
DB_RETAIN_DAYS = 14  # articles older than this are pruned daily

# ── Auto-summarization settings ──────────────────────────────────
AUTO_SUMMARIZE_TOP_N   = 5    # summarize the top N clusters each cycle
AUTO_SUMMARIZE_MIN_SRC = 2    # only clusters with 2+ sources get synthesis
AUTO_SUMMARIZE_DELAY   = 1.5  # seconds between API calls (rate limit protection)

# ── API limits ────────────────────────────────────────────────────
API_MAX_PAGE = 1000           # Maximum page number for pagination
API_MAX_Q_LEN = 500           # Maximum search query length

RSS_FEEDS = [
    ("Sloboden Pecat",  "https://slobodenpecat.mk/feed/"),
    ("Kanal 5",         "https://kanal5.com.mk/rss.aspx?id=1"),
    ("MIA",             "https://mia.mk/feed"),
    ("Sitel",           "https://sitel.com.mk/rss.xml"),
    ("Telma",           "https://telma.com.mk/feed/"),
    ("Kurir",           "https://kurir.mk/feed/"),
    ("Republika",       "https://republika.mk/feed/"),
    ("Fokus",           "https://fokus.mk/feed/"),
    ("Nezavisen",       "https://nezavisen.mk/feed/"),
    ("Faktor",          "https://faktor.mk/rss"),
    ("Vecer",           "https://vecer.mk/feed/"),
    ("Meta",            "https://meta.mk/feed/"),
    ("360 Stepeni",     "https://360stepeni.mk/feed/"),
    ("Makfax",          "https://makfax.com.mk/feed/"),
    ("Nova Makedonija", "https://novamakedonija.com.mk/feed/"),
    ("Infomax",         "https://infomax.mk/feed/"),
    ("Press24",         "https://press24.mk/feed/"),
    ("Skopje1",         "https://skopje1.mk/feed/"),
    ("Plusinfo",        "https://plusinfo.mk/feed/"),
    ("Lokalno",         "https://lokalno.mk/feed/"),
    ("4News",           "https://4news.mk/feed/"),
    ("Makpress",        "https://makpress.mk/feed/"),
    ("Vistinomer",      "https://vistinomer.mk/feed/"),
    ("Lider",           "https://lider.mk/feed/"),
    ("MKD",             "https://mkd.mk/feed/"),
    ("NetPress",        "https://netpress.com.mk/feed/"),
    ("Akademik",        "https://akademik.mk/feed/"),
    ("Skopje Info",     "https://skopjeinfo.mk/feed/"),
    ("Prizma",          "https://prizma.mk/feed/"),
    ("Expres",          "https://expres.mk/feed/"),
    ("Tetovo Info",     "https://tetovoinfo.mk/feed/"),
    ("A1on",            "https://a1on.mk/feed/"),
    ("SportSport",      "https://sportsport.mk/feed/"),
    ("Strumica Info",   "https://strumicainfo.mk/feed/"),
    ("24 Вести",        "https://24.mk/feed/"),
    ("TV21",            "https://tv21.mk/feed/"),
    ("Слободна Европа", "https://www.slobodnaevropa.mk/api/zryoyqpmou"),
    ("Deutsche Welle",  "http://rss.dw-world.de/syndication/feeds/dwworld.maz.xml"),
    ("Civil Media",     "https://civilmedia.mk/feed/"),
    ("Радио МОФ",       "https://radiomof.mk/feed/"),
    ("Сакам да кажам",  "https://sdk.mk/feed/"),
    ("Бизнис Вести",    "https://biznisvesti.mk/feed/"),
    ("Ohrid News",      "https://ohridnews.mk/feed/"),
    ("Vecer Sport",     "https://sport.vecer.mk/feed/"),
    ("Ekonomija",       "https://ekonomija.com.mk/feed/"),
    ("Zdravje",         "https://zdravje.com.mk/feed/"),
    ("MRT",             "https://mrt.com.mk/rss"),
    ("Kolumna",         "https://kolumna.mk/feed/"),
    ("Okno",            "https://okno.mk/feed/"),
    ("Alfa TV",         "https://alfa.mk/feed/"),
    ("Tocka",           "https://tocka.com.mk/rss"),
    ("IRL",             "https://irl.mk/mk/feed/"),
    ("Nova TV",         "https://novatv.mk/feed/"),
    ("Libertas",        "https://libertas.mk/feed/"),
    ("Racin",           "https://racin.mk/feed/"),
    ("Kajgana",         "https://kajgana.com/rss.xml"),
    ("Pari.com.mk",     "https://pari.com.mk/feed/"),
    ("Bloomberg Adria", "https://mk.bloombergadria.com/rss"),
    ("E-Magazin",       "https://emagazin.mk/feed/"),
    ("IT.mk",           "https://it.mk/feed/"),
    ("Sportmanija",     "https://sportmanija.mk/feed/"),
    ("Fakulteti",       "https://fakulteti.mk/rss"),
    ("Magazin",         "https://magazin.mk/feed/"),
]

HARDCODED_FEED_CATEGORIES: dict[str, str] = {}

CURATED_INTERNATIONAL_SOURCES = (
    "N1 Info",
    "Klix.ba",
    "Index.hr",
    "Jutarnji",
    "Vijesti.me",
    "EuroNews",
    "BBC News",
    "Deutsche Welle EN",
    "Deutsche Welle DE",
    "FAZ",
    "Reuters",
    "AP News",
)

# Specific per-source limits to prevent low-quality aggregators from flooding the system
SOURCE_LIMITS = {
    "Kurir": 5,
    "Republika": 5,
    "Infomax": 5,
    "Sitel": 8,
    "Kanal 5": 8
}

MK_LANGUAGE_SOURCES: frozenset[str] = frozenset({
    "Sloboden Pecat", "Kanal 5", "MIA", "Sitel", "Telma", "Kurir",
    "Republika", "Fokus", "Nezavisen", "Faktor", "Vecer", "Meta",
    "360 Stepeni", "Makfax", "Nova Makedonija", "Infomax", "Press24",
    "Skopje1", "Plusinfo", "Lokalno", "4News", "Makpress", "Vistinomer",
    "Lider", "MKD", "Akademik", "Skopje Info",
    "Prizma", "Expres", "Tetovo Info", "A1on", "SportSport",
    "Strumica Info", "24 Вести", "TV21", "Слободна Европа",
    "Deutsche Welle", "Civil Media", "Радио МОФ",
    "Сакам да кажам", "Бизнис Вести", "Ohrid News", "Vecer Sport",
    "Ekonomija", "Zdravje", "MRT", "Time.mk", "Kolumna", "Okno",
    "Alfa TV", "Tocka", "IRL", "Nova TV", "Libertas", "Racin",
    "Kajgana", "Pari.com.mk", "Bloomberg Adria", "E-Magazin",
    "IT.mk", "Sportmanija", "Fakulteti", "Magazin",
})

DIASPORA_FEEDS = [
    ("Tagesschau",          "https://www.tagesschau.de/xml/rss2",                               "Германија"),
    ("Der Spiegel",         "https://www.spiegel.de/schlagzeilen/index.rss",                    "Германија"),
    ("Deutsche Welle DE",   "https://rss.dw.com/rdf/rss-de-all",                               "Германија"),
    ("Deutsche Welle EN",   "https://rss.dw.com/rdf/rss-en-ger",                               "Германија"),
    ("ZDF Heute",           "https://www.zdf.de/rss/zdf/nachrichten",                          "Германија"),
    ("Süddeutsche Zeitung", "https://rss.sueddeutsche.de/rss/Topthemen",                       "Германија"),
    ("Die Zeit",            "https://newsfeed.zeit.de/index",                                   "Германија"),
    ("SRF News",    "https://www.srf.ch/news/bnf/rss/1890",                                     "Европа"),
    ("20 Minuten",  "https://www.20min.ch/rss/rss.tmpl?type=channel&get=4",                     "Европа"),
    ("CNN",         "http://rss.cnn.com/rss/cnn_topstories.rss",                                 "Америка"),
    ("NPR",         "https://feeds.npr.org/1001/rss.xml",                                        "Америка"),
    ("Reuters",     "https://www.reutersagency.com/feed/",                                       "Свет"),
    ("CBC News",        "https://rss.cbc.ca/lineup/topstories.xml",                             "Америка"),
    ("Fox News Latest", "https://moxie.foxnews.com/google-publisher/latest.xml",                "Америка"),
    ("Fox News World",  "https://moxie.foxnews.com/google-publisher/world.xml",                 "Америка"),
    ("BBC US/Canada",   "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",            "Америка"),
    ("BBC News",        "https://feeds.bbci.co.uk/news/rss.xml",                                "Европа"),
    ("The Guardian",    "https://www.theguardian.com/world/rss",                                "Европа"),
    ("France24",        "https://www.france24.com/en/europe/rss",                               "Европа"),
    ("EuroNews",        "https://feeds.feedburner.com/euronews/en/home/",                       "Европа"),
    ("Politico Europe", "https://www.politico.eu/feed",                                         "Европа"),
    ("ABC Australia",   "https://www.abc.net.au/news/feed/2942460/rss.xml",                     "Свет"),
    ("Al Jazeera",      "https://www.aljazeera.com/xml/rss/all.xml",                            "Свет"),
    ("SCMP",            "https://www.scmp.com/rss/91/feed",                                     "Свет"),
    ("NHK World",       "https://www3.nhk.or.jp/rss/news/cat0.xml",                             "Свет"),
    ("Times of India",  "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",           "Свет"),
    ("RFI English",     "https://www.rfi.fr/en/rss",                                            "Свет"),
    ("ANSA",        "https://www.ansa.it/sito/ansait_rss.xml",                                   "Европа"),
    ("RTVSLO",      "https://www.rtvslo.si/feeds/00.xml",                                       "Словенија"),
    ("ORF",         "https://rss.orf.at/news.xml",                                               "Австрија"),
    ("SVT News",    "https://www.svt.se/nyheter/rss.xml",                                        "Шведска"),
    ("N1 Info",     "https://n1info.rs/feed/",                                                   "Балкан"),
    ("B92",         "https://www.b92.net/info/rss/vesti.xml",                                    "Балкан"),
    ("Kurir.rs",     "https://www.kurir.rs/rss",                                                 "Балкан"),
    ("Blic.rs",      "https://www.blic.rs/rss",                                                  "Балкан"),
    ("Novinite",    "https://www.novinite.com/rss.php",                                          "Балкан"),
    ("Dnevnik.bg",  "https://www.dnevnik.bg/rss/",                                              "Балкан"),
    ("Kathimerini", "https://www.ekathimerini.com/rss",                                          "Балкан"),
    ("RTS",         "https://www.rts.rs/rss/vesti",                                             "Балкан"),
    ("FAZ",         "https://www.faz.net/rss/aktuell",                                          "Германија"),
    ("Swissinfo",   "https://www.swissinfo.ch/eng/rss",                                         "Швајцарија"),
    ("AP News",     "http://associated-press.s3-website-us-east-1.amazonaws.com/topnews.xml",    "Америка"),
    ("The Verge",   "https://www.theverge.com/rss/index.xml",                                   "Свет"),
    ("Ars Technica","https://feeds.arstechnica.com/arstechnica/index",                          "Свет"),
    ("TechCrunch",  "https://techcrunch.com/feed/",                                             "Свет"),
    ("Axios",       "https://www.axios.com/feeds/feed.rss",                                     "Свет"),
    ("ESPN",        "https://www.espn.com/espn/rss/news",                                       "Свет"),
    ("Exit News",   "https://exit.al/en/feed/",                                                  "Балкан"),
    ("Balkan Insight", "https://balkaninsight.com/feed/",                                        "Балкан"),
    ("Слободна Европа Balkan", "https://www.slobodnaevropa.org/api/z-pq_te_iqpp",                "Балкан"),

    ("Daily Sabah",  "https://www.dailysabah.com/rssFeed/politics",                              "Балкан"),
    ("TRT World",    "https://www.trtworld.com/content/rss.xml",                                 "Балкан"),
    ("Index.hr",     "https://index.hr/rss",                                                     "Балкан"),
    ("Jutarnji",     "https://www.jutarnji.hr/feed",                                             "Балкан"),
    ("Klix.ba",      "https://www.klix.ba/rss",                                                  "Балкан"),
    ("Vijesti.me",   "https://www.vijesti.me/rss",                                               "Балкан"),
]

SOURCE_CREDIBILITY = {
    "MIA": 2.0, "MRT": 1.8, "Sitel": 1.7, "Kanal 5": 1.7, "Telma": 1.6, "Alfa TV": 1.5,
    "Sloboden Pecat": 1.5, "Nova Makedonija": 1.5, "Republika": 1.4, "Makfax": 1.4,
    "Fokus": 1.3, "Nezavisen": 1.3, "Kurir": 1.2, "Faktor": 1.2, "Vecer": 1.2, "Meta": 1.2,
    "360 Stepeni": 1.1, "Infomax": 1.1, "Lider": 1.1, "Vistinomer": 1.8, "Birn": 1.3,
    "Akademik": 1.1, "NetPress": 1.0, "MKD": 1.0, "Press24": 0.9,
    "Skopje1": 0.9, "Plusinfo": 0.9, "Lokalno": 0.9, "4News": 0.9, "Makpress": 0.9,
    "Skopje Info": 0.8, "Prizma": 0.8, "Expres": 0.8, "Tetovo Info": 0.8,
    "A1on": 0.8, "SportSport": 0.8, "Strumica Info": 0.8, "24 Вести": 1.6, "TV21": 1.6,
    "Слободна Европа": 1.8, "Deutsche Welle": 1.7, "Civil Media": 1.3,
    "Радио МОФ": 1.1, "Сакам да кажам": 1.1, "Бизнис Вести": 1.0, "Ohrid News": 0.8,
    "Vecer Sport": 1.0, "Ekonomija": 0.9, "Zdravje": 0.8, "Time.mk": 1.1, "Kolumna": 0.9,
    "Okno": 1.0, "Tocka": 1.1, "IRL": 1.8, "Nova TV": 1.3, "Libertas": 1.1, "Racin": 1.3,
    "Kajgana": 1.0, "Pari.com.mk": 1.2, "Bloomberg Adria": 1.4, "E-Magazin": 1.1,
    "IT.mk": 1.1, "Sportmanija": 0.8, "Fakulteti": 1.1, "Magazin": 0.8,
    "Tagesschau": 1.8, "Der Spiegel": 1.7, "SRF News": 1.7, "20 Minuten": 1.2,
    "CNN": 1.6, "NPR": 1.6, "Reuters": 1.9, "CBC News": 1.7, "BBC News": 1.8,
    "The Guardian": 1.7, "ABC Australia": 1.6, "ANSA": 1.6, "RTVSLO": 1.7,
    "ORF": 1.7, "SVT News": 1.7, "Top Channel": 1.6, "N1 Info": 1.5, "B92": 1.4,
    "Novinite": 1.2, "Kathimerini": 1.5, "Exit News": 1.3,
    "FAZ": 1.8, "Swissinfo": 1.8, "AP News": 1.9, "RTS": 1.6, "Dnevnik.bg": 1.5,
    "The Verge": 1.4, "TechCrunch": 1.4, "Axios": 1.7, "Ars Technica": 1.6, "ESPN": 1.6,
    "Слободна Европа Balkan": 1.7,
    "Daily Sabah": 1.4, "TRT World": 1.6, "Balkan Insight": 1.7, "Kurir.rs": 1.2,
    "Blic.rs": 1.3, "Index.hr": 1.5, "Jutarnji": 1.4, "Klix.ba": 1.4, "Vijesti.me": 1.3,
}
DEFAULT_CREDIBILITY = 0.8

SOURCE_CATEGORIES = {
    "MIA": "Агенциски", "MRT": "Јавен Сервис", "Sitel": "Главни", "Kanal 5": "Главни",
    "Telma": "Главни", "24 Вести": "Главни", "TV21": "Главни",
    "Sloboden Pecat": "Независни", "Fokus": "Независни", "Nezavisen": "Независни",
    "Meta": "Независни", "360 Stepeni": "Независни", "IRL": "Истражувачки",
    "Makfax": "Агенциски", "NetPress": "Алтернативни", "Kurir": "Алтернативни",
    "Republika": "Алтернативни", "Infomax": "Алтернативни",
    "Deutsche Welle": "Меѓународни", "Слободна Европа": "Меѓународни",
    "CNN": "Меѓународни", "BBC News": "Меѓународни", "Reuters": "Меѓународни",
    "The Guardian": "Меѓународни", "Al Jazeera": "Меѓународни"
}
DEFAULT_SOURCE_CATEGORY = "Локални"

# ── Ingestion Quality Settings ──────────────────────────────────
JUNK_KEYWORDS = [
    "хороскоп", "временска прогноза", "виц на денот", "на денешен ден", 
    "дневно мени", "рецепт на денот", "курсна листа", "лото резултати",
    "го извлековме среќниот добитник"
]

# ── Balanced Coverage Settings ──────────────────────────────────
BALANCED_COVERAGE_THRESHOLD = 3 # clusters with 3+ diverse sources get a badge

# ── Telegram Configuration ───────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "") 

# ── OpenClaw Gateway Configuration ──────────────────────────────
OPENCLAW_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")

# ── Cloudflare R2 Configuration ──────────────────────────────────
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "presek-cache")

# ── Image Generation Configuration ──────────────────────────────
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")
