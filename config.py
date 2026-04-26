import os
import sys
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # Optional in pre-provisioned environments.
    def load_dotenv():
        return False

# Load environment variables from .env file
load_dotenv()

REQUIRED_RUNTIME_ENV_KEYS = ("DATABASE_URL", "SECRET_KEY")


def validate_required_env(required_keys=REQUIRED_RUNTIME_ENV_KEYS):
    """Validate that critical environment variables are set before serving traffic."""
    missing = [k for k in required_keys if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "presek-mk-vesti")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS = {"sub": "mailto:admin@presek.live"}

# ── Additional AI Providers (OpenAI-compatible) ──────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
CEREBRAS_API_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODEL = "llama3.1-8b"

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-large-latest"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/auto"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

REFRESH_INTERVAL = 300
FEED_LIMIT = 10
AI_DAILY_LIMIT = 1000000
CLUSTER_LOOKBACK = 500  # increased from 200 — handles 36 sources × 10 entries per refresh
BREAKING_SCORE_THRESHOLD = 4.5
DB_RETAIN_DAYS = 180 # articles older than this are pruned daily

# ── Auto-summarization settings ──────────────────────────────────
AUTO_SUMMARIZE_TOP_N   = 25   # summarize the top N clusters each cycle
AUTO_SUMMARIZE_MIN_SRC = 2    # only clusters with 2+ sources get synthesis
AUTO_SUMMARIZE_DELAY   = 1.5  # seconds between API calls (rate limit protection)

# ── API limits ────────────────────────────────────────────────────
API_MAX_PAGE = 1000           # Maximum page number for pagination
API_MAX_Q_LEN = 500           # Maximum search query length

# Source inventory is seeded into the database from source_catalog.py.
# Runtime source state should come from the sources table, not app config.

HARDCODED_FEED_CATEGORIES: dict[str, str] = {}

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
    "Skopje1", "Plusinfo", "4News", "Makpress", "Vistinomer",
    "Lider", "MKD", "NetPress", "Akademik", "Skopje Info",
    "Prizma", "Expres", "Tetovo Info", "A1on", "SportSport",
    "24 Вести", "TV21", "Civil Media", "Радио МОФ",
    "Сакам да кажам", "Бизнис Вести", "MRT", "Okno",
    "Alfa TV", "Tocka", "IRL", "Nova TV", "Libertas", "Racin",
    "Kajgana", "Pari.com.mk", "E-Magazin",
    "IT.mk", "Sportmanija",
    "Reporter", "Off.net.mk", "Denesen", "24info",
    "Vreme", "Frontline", "Nacional", "Antropol", "Brif",
    "Pressing TV", "Inbox7", "Kanal77", "Glas", "Vistina",
    "Vesnik", "Sloboden Svet", "BiznisInfo", "Bitola News",
    "PopUp", "Kultura.mk", "Reper",
})

DIASPORA_FEEDS = []

SOURCE_CREDIBILITY = {
    # MK sources
    "MIA": 2.0, "MRT": 1.8, "Sitel": 1.7, "Kanal 5": 1.7, "Telma": 1.6, "Alfa TV": 1.5,
    "Sloboden Pecat": 1.5, "Nova Makedonija": 1.5, "Republika": 1.4, "Makfax": 1.4,
    "Fokus": 1.3, "Nezavisen": 1.3, "Kurir": 1.2, "Faktor": 1.2, "Vecer": 1.2, "Meta": 1.2,
    "360 Stepeni": 1.1, "Infomax": 1.1, "Lider": 1.1, "Vistinomer": 1.8, "Birn": 1.3,
    "Akademik": 1.1, "NetPress": 1.0, "MKD": 1.0, "Press24": 0.9,
    "Skopje1": 0.9, "Plusinfo": 0.9, "4News": 0.9, "Makpress": 0.9,
    "Skopje Info": 0.8, "Prizma": 0.8, "Expres": 0.8, "Tetovo Info": 0.8,
    "A1on": 0.8, "SportSport": 0.8, "24 Вести": 1.6, "TV21": 1.6,
    "Civil Media": 1.3,
    "Радио МОФ": 1.1, "Сакам да кажам": 1.1, "Бизнис Вести": 1.0,
    "Okno": 1.0, "Tocka": 1.1, "IRL": 1.8, "Nova TV": 1.3, "Libertas": 1.1, "Racin": 1.3,
    "Kajgana": 1.0, "Pari.com.mk": 1.2, "E-Magazin": 1.1,
    "IT.mk": 1.1, "Sportmanija": 0.8,
    "Reporter": 1.0, "Off.net.mk": 1.0, "Denesen": 0.9,
    "24info": 0.9, "Vreme": 0.9, "Frontline": 0.9, "Nacional": 0.8,
    "Antropol": 1.1, "Brif": 0.9, "Pressing TV": 1.2, "Inbox7": 0.9,
    "Kanal77": 1.0, "Glas": 0.8, "Vistina": 0.8,
    "Vesnik": 0.9, "Sloboden Svet": 0.8, "BiznisInfo": 1.0, "Bitola News": 0.8,
    "PopUp": 1.1, "Kultura.mk": 1.2, "Reper": 1.1,
}
DEFAULT_CREDIBILITY = 0.8

SOURCE_CATEGORIES = {
    "MIA": "Агенциски", "MRT": "Јавен Сервис", "Sitel": "Главни", "Kanal 5": "Главни",
    "Telma": "Главни", "24 Вести": "Главни", "TV21": "Главни",
    "Sloboden Pecat": "Независни", "Fokus": "Независни", "Nezavisen": "Независни",
    "Meta": "Независни", "360 Stepeni": "Независни", "IRL": "Истражувачки",
    "Makfax": "Агенциски", "NetPress": "Алтернативни", "Kurir": "Алтернативни",
    "Republika": "Алтернативни", "Infomax": "Алтернативни",
    "Pressing TV": "Главни", "Antropol": "Независни",
    "Bitola News": "Регионални",
    "PopUp": "Култура", "Kultura.mk": "Култура",
    "Reper": "Култура",
}
DEFAULT_SOURCE_CATEGORY = "Локални"

# ── Ingestion Quality Settings ──────────────────────────────────
JUNK_KEYWORDS = [
    "хороскоп", "временска прогноза", "виц на денот", "на денешен ден", 
    "дневно мени", "рецепт на денот", "курсна листа", "лото резултати",
    "го извлековме среќниот добитник", "ѕвездите им ветуваат", "хороскопски знаци",
    "неделен хороскоп", "дневен хороскоп", "месечен хороскоп",
    "го извлековме", "извлекување лото", "наградни игри", "што велат ѕвездите",
    "ѕвездите предвидуваат", "пари и просперитет", "среќни датуми"
]

# ── Balanced Coverage Settings ──────────────────────────────────
BALANCED_COVERAGE_THRESHOLD = 3 # clusters with 3+ diverse sources get a badge

# ── Image Generation Configuration ──────────────────────────────
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")

# ── Performance & Resource Management ───────────────────────────
# Large models (Gemma 2, MiniLM) take 2GB+ RAM and can slow down the server.
# Set to False to disable local translation/style normalization.
LOCAL_TRANSLATION_ENABLED = os.environ.get("LOCAL_TRANSLATION_ENABLED", "true").lower() == "true"
ENABLE_EXPENSIVE_STYLE_TASKS = os.environ.get("ENABLE_EXPENSIVE_STYLE_TASKS", "false").lower() == "true"

# ── AI Routing Configuration ────────────────────────────────────
# local (Gemma 2 2B) is now the PRIMARY choice for volume tasks.
# mistral (Cloud) is the HIGH-TIER fallback or for complex synthesis.
TASK_ROUTING = {
    "translation":  ["local", "mistral"],
    "summarize":    ["local", "mistral"],
    "synthesis":    ["local", "mistral"],
    "daily_brief":  ["local", "mistral"],
    "research":     ["local", "mistral"],
    "chat":         ["local", "mistral"],
    "default":      ["local", "mistral"],
}
# ── Clustering Parameters ───────────────────────────────────────
CLUSTERING_THRESHOLDS = {
    "SIMILARITY_THRESHOLD": 0.45,
    "VECTOR_THRESHOLD": 0.28,
    "MAX_CLUSTER_SIZE": 35
}
