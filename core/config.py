import logging
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # Optional in pre-provisioned environments.

    def load_dotenv(*_args, **_kwargs):
        return False


# Load environment variables from .env file (only in development)
# In production, environment variables should be set directly
if os.environ.get("ENV") != "production":
    load_dotenv(override=True)

# Configure logging for config validation
log = logging.getLogger("presek.config")

REQUIRED_RUNTIME_ENV_KEYS = ("DATABASE_URL", "SECRET_KEY")

# Optional but recommended for production
RECOMMENDED_ENV_KEYS = (
    "REDIS_URL",
    "JWT_SECRET",
    "NTFY_TOPIC",
    "NTFY_TOKEN",
    "SMTP_HOST",
    "SMTP_PASS",
)

# Keys that should NEVER be used without explicit configuration
SENSITIVE_ENV_KEYS = (
    "DATABASE_URL",
    "REDIS_URL",
    "SECRET_KEY",
    "JWT_SECRET",
    "SMTP_PASS",
    "CLOUDFLARE_API_TOKEN",
    "R2_SECRET_ACCESS_KEY",
    "CF_AI_GATEWAY_TOKEN",
)


def validate_required_env(required_keys=REQUIRED_RUNTIME_ENV_KEYS):
    """Validate that critical environment variables are set before serving traffic."""
    missing = [k for k in required_keys if not os.environ.get(k)]
    if missing:
        # In production, this should be a hard failure
        if os.environ.get("ENV") == "production":
            missing_str = ", ".join(missing)
            log.critical(f"PRODUCTION STARTUP FAILED: Missing required environment variables: {missing_str}")
            raise RuntimeError(f"Missing required environment variables: {missing_str}")
        else:
            # In development, log warnings but allow startup
            for key in missing:
                log.warning(f"Missing environment variable (required for production): {key}")
            log.warning(f"Running in development mode with missing config. For production, set: {', '.join(missing)}")


def validate_recommended_env():
    """Warn about missing recommended configuration."""
    missing = [k for k in RECOMMENDED_ENV_KEYS if not os.environ.get(k)]
    if missing:
        for key in missing:
            log.warning(f"Recommended environment variable not set: {key}")


def check_sensitive_values():
    """Warn if sensitive environment variables contain default/test values."""
    dangerous_patterns = [
        ("DATABASE_URL", ["password", "1234", "changeme"]),
        ("SECRET_KEY", ["secret", "test", "changeme", "123"]),
        ("PRESEK_ADMIN_TOKEN", ["admin", "test", "123", "changeme"]),
    ]

    issues = []
    for key, patterns in dangerous_patterns:
        value = os.environ.get(key, "").lower()
        for pattern in patterns:
            if pattern.lower() in value:
                issues.append(f"{key} appears to contain a default/test value")
                break

    if issues:
        log.warning(f"Potentially insecure configuration detected: {'; '.join(issues)}")


# Validate on import
def _init_config():
    """Initialize and validate configuration on module import."""
    validate_required_env()
    validate_recommended_env()

    # Only check in development (production should have proper values)
    if os.environ.get("ENV") != "production":
        check_sensitive_values()

    # Validate specific configurations
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url and not db_url.startswith(("postgresql://", "postgres://")):
        log.error(f"Invalid DATABASE_URL scheme: {db_url[:50]}...")
        raise ValueError("DATABASE_URL must use postgresql:// or postgres:// scheme")


# Run initialization
_init_config()

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "presek.live-vesti")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")
PRESEK_ADMIN_TOKEN = os.environ.get("PRESEK_ADMIN_TOKEN", "")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

# Master runtime kill-switch for all LLM inference (local and remote).
# Disabled by default: no provider calls are made and AI generation no-ops.
# Set PRESEK_AI_ENABLED=1 to re-enable.
AI_ENABLED = os.environ.get("PRESEK_AI_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")

# ── Full-text transparency mode ─────────────────────────────
# When enabled, crawl_article_task persists the extracted article body into
# articles.full_content (per-source gated by sources.full_text_allowed).
FULLTEXT_ENABLED = os.environ.get("FULLTEXT_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
FULLTEXT_MAX_CHARS = int(os.environ.get("FULLTEXT_MAX_CHARS", "20000"))

# MK-only product: ingest only Macedonian sources and never translate.
MK_ONLY = os.environ.get("MK_ONLY", "true").strip().lower() in ("1", "true", "yes", "on")

# Default language for API endpoints when the caller omits `lang`.
# The deployment is MK-only and the Serbian dataset was purged, so "sr" filters
# (country='RS') match no rows and silently return empty responses. Keep this in
# sync with MK_ONLY: MK deployment -> "mk".
DEFAULT_LANG = os.environ.get("PRESEK_DEFAULT_LANG", "mk" if MK_ONLY else "sr")

# Identifying crawler UA (robots.txt compliance / attribution friendliness).
BOT_USER_AGENT = os.environ.get(
    "BOT_USER_AGENT",
    "PresekBot/1.0 (+https://presek.mk/bot; bot@presek.mk)",
)

REFRESH_INTERVAL = 300
FEED_LIMIT = 10
AI_DAILY_LIMIT = 1000000
CLUSTER_LOOKBACK = 300  # Narrowed to reduce memory pressure
BREAKING_SCORE_THRESHOLD = 4.5
DB_RETAIN_DAYS = 90  # articles older than this are pruned daily
DB_RETAIN_FAILED_TASKS_DAYS = 360  # failed tasks older than this are pruned daily

# ── Language Configuration ──────────────────────────────────
LANGUAGE_CONFIG = {
    "sr": {
        "stemmer_suffixes": [
            "ovanje",
            "anje",
            "enje",
            "isti",
            "istot",
            "ista",
            "ski",
            "skih",
            "skog",
            "skom",
            "ska",
            "sko",
            "ovski",
            "ovska",
            "ovsko",
            "evski",
            "evska",
            "evsko",
            "nji",
            "njeg",
            "njoj",
            "njim",
            "njih",
            "ni",
            "ti",
            "te",
            "tu",
            "at",
            "et",
            "it",
            "ov",
            "ev",
            "iv",
            "an",
            "en",
            "on",
        ],
        "stopwords": {
            "i",
            "na",
            "u",
            "od",
            "sa",
            "za",
            "se",
            "e",
            "ne",
            "da",
            "po",
            "do",
            "pri",
            "no",
            "ili",
            "ako",
            "sto",
            "ko",
            "koji",
            "koja",
            "koje",
            "iz",
            "o",
            "je",
            "su",
            "a",
            "pred",
            "pod",
            "nad",
            "zad",
            "medju",
            "ovaj",
            "ova",
            "ovo",
            "ono",
            "evo",
            "ove",
            "ovi",
            "taj",
            "ta",
            "to",
            "ti",
            "jedan",
            "jedna",
            "jedno",
            "nema",
            "novi",
            "nov",
            "nova",
            "samo",
            "jos",
            "preko",
            "buduci",
            "zbog",
            "gde",
            "kako",
            "kad",
            "tok",
            "pak",
            "ipak",
            "zato",
            "ovakav",
            "ovakva",
            "ovakvi",
            "prema",
            "saopstenja",
            "informisu",
            "izjave",
            "veli",
            "izjavili",
            "rece",
            "porucuje",
            "kazu",
            "prenose",
            "objavi",
            "pise",
            "danas",
            "juce",
            "sutra",
            "Srbija",
            "severna",
            "sad",
            "kina",
            "eu",
            "nato",
            "the",
            "and",
            "for",
            "from",
            "that",
            "this",
            "with",
            "has",
        },
    },
    "mk": {
        "stemmer_suffixes": [
            "ovanje",
            "anje",
            "enje",
            "isti",
            "istot",
            "ista",
            "ski",
            "skih",
            "skog",
            "skom",
            "ska",
            "sko",
            "ovski",
            "ovska",
            "ovsko",
            "evski",
            "evska",
            "evsko",
            "nji",
            "njeg",
            "njoj",
            "njim",
            "njih",
            "ni",
            "ti",
            "te",
            "tu",
            "at",
            "et",
            "it",
            "ov",
            "ev",
            "iv",
            "an",
            "en",
            "on",
        ],
        "stopwords": {
            "и",
            "на",
            "во",
            "од",
            "со",
            "за",
            "се",
            "е",
            "не",
            "да",
            "по",
            "до",
            "при",
            "но",
            "или",
            "ако",
            "што",
            "ко",
            "кој",
            "која",
            "кое",
            "из",
            "о",
            "е",
            "се",
            "а",
            "пред",
            "под",
            "над",
            "зад",
            "меѓу",
            "овој",
            "ова",
            "оваа",
            "овие",
            "тој",
            "таа",
            "тоа",
            "тие",
            "еден",
            "една",
            "едно",
            "нема",
            "нови",
            "нов",
            "нова",
            "само",
            "уште",
            "преку",
            "бидејќи",
            "поради",
            "каде",
            "како",
            "кога",
            "тек",
            "пак",
            "сепак",
            "затоа",
            "ваков",
            "ваква",
            "вакви",
            "према",
            "соопштенија",
            "информираат",
            "изјави",
            "вели",
            "изјавија",
            "рече",
            "порачува",
            "кажуваат",
            "пренесуваат",
            "објави",
            "пишува",
            "денес",
            "вчера",
            "утре",
            "Македонија",
            "северна",
            "сад",
            "кина",
            "еу",
            "нато",
        },
    },
}

AUTO_SUMMARIZE_TOP_N = int(os.environ.get("AUTO_SUMMARIZE_TOP_N", "20"))
AUTO_SUMMARIZE_MIN_SRC = int(os.environ.get("AUTO_SUMMARIZE_MIN_SRC", "2"))
AUTO_SUMMARIZE_DELAY = float(os.environ.get("AUTO_SUMMARIZE_DELAY", "1.5"))
AUTO_SUMMARIZE_FRESH_HOURS = int(os.environ.get("AUTO_SUMMARIZE_FRESH_HOURS", "6"))
HOMEPAGE_SYNTHESIS_ONLY = os.environ.get("HOMEPAGE_SYNTHESIS_ONLY", "true").lower() in (
    "1",
    "true",
    "yes",
)
HOMEPAGE_SYNTHESIS_PRIORITIZE_LIMIT = int(os.environ.get("HOMEPAGE_SYNTHESIS_PRIORITIZE_LIMIT", "24"))
HOMEPAGE_SYNTHESIS_PRIORITIZE_INTERVAL_SECONDS = float(
    os.environ.get("HOMEPAGE_SYNTHESIS_PRIORITIZE_INTERVAL_SECONDS", "300")
)
HOMEPAGE_SYNTHESIS_QUEUE_HEADROOM = int(os.environ.get("HOMEPAGE_SYNTHESIS_QUEUE_HEADROOM", "60"))

# ── API limits ────────────────────────────────────────────────────
API_MAX_PAGE = 1000  # Maximum page number for pagination
API_MAX_Q_LEN = 500  # Maximum search query length

# Source inventory is seeded into the database from source_catalog.py.
# Runtime source state should come from the sources table, not app config.

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
SOURCE_LIMITS = {"Kurir": 5, "Informer": 5, "Alo": 5, "Republika": 5, "Telegraf": 8}

SR_LANGUAGE_SOURCES: frozenset[str] = frozenset(
    {
        "Blic",
        "Kurir",
        "Telegraf",
        "Informer",
        "Alo",
        "N1 Info",
        "nova.rs",
        "danas",
        "RTS",
        "Vreme",
        "B92",
        "Mondo",
        "Politika",
        "Novosti",
        "021",
        "Srbija danas",
        "Republika",
        "NIN",
        "Nedeljnik",
        "Euronews Srbija",
        "021.rs",
        "Insajder",
        "KRIK",
    }
)

DIASPORA_FEEDS = []

SOURCE_CREDIBILITY = {
    # SR sources
    "N1 Info": 1.9,
    "nova.rs": 1.8,
    "danas": 1.9,
    "RTS": 1.7,
    "Vreme": 1.9,
    "NIN": 1.9,
    "Nedeljnik": 1.8,
    "Politika": 1.6,
    "B92": 1.5,
    "Blic": 1.4,
    "Euronews Srbija": 1.7,
    "021.rs": 1.7,
    "Insajder": 1.9,
    "KRIK": 1.9,
    "Telegraf": 1.0,
    "Kurir": 0.9,
    "Alo": 0.8,
    "Informer": 0.7,
    "Srbija danas": 0.9,
    "Republika": 0.8,
    "Mondo": 1.2,
    "Novosti": 1.4,
}
DEFAULT_CREDIBILITY = 0.8

SOURCE_CATEGORIES = {
    "N1 Info": "Nezavisni",
    "nova.rs": "Nezavisni",
    "danas": "Nezavisni",
    "RTS": "Javni Servis",
    "Vreme": "Istraživački",
    "NIN": "Istraživački",
    "Nedeljnik": "Istraživački",
    "Politika": "glavni",
    "B92": "glavni",
    "Blic": "glavni",
    "Euronews Srbija": "glavni",
    "Insajder": "Istraživački",
    "KRIK": "Istraživački",
    "Telegraf": "Tabloidi",
    "Kurir": "Tabloidi",
    "Alo": "Tabloidi",
    "Informer": "Tabloidi",
    "Srbija danas": "Tabloidi",
    "Republika": "Tabloidi",
    "Mondo": "glavni",
    "Novosti": "glavni",
    # Macedonian sources
    "MKD.mk": "glavni",
    "Meta.mk": "Agencijski",
    "Kapital": "Nezavisni",
    "Radio Slobodna Evropa MK": "Nezavisni",
    "Denar.mk": "Nezavisni",
    "Denar": "Nezavisni",
    "A1on": "glavni",
    "Time.mk": "glavni",
    "SakamDaKazam.mk": "Istraživački",
    "Sitel": "Javni Servis",
    "Telma": "Javni Servis",
    "Alsat": "Javni Servis",
    "Kanal 5": "Javni Servis",
    "MRT": "Javni Servis",
    "Makfax": "Agencijski",
    "Kurir.mk": "glavni",
    "Nezavisen.mk": "glavni",
    "PlusInfo": "glavni",
    "Vecer": "glavni",
    "Fokus": "Nezavisni",
    "360 Stepeni": "Istraživački",
    "Vistinomer": "Istraživački",
    "CivilMedia.mk": "Nezavisni",
    "Sloboden Pecat": "glavni",
    "Radio MOF": "Nezavisni",
    "Okno.mk": "Nezavisni",
    "Nova Makedonija": "glavni",
    "Libertas": "Nezavisni",
    "Infomax.mk": "Tabloidi",
    "Zase.mk": "Tabloidi",
    "Lider.mk": "Tabloidi",
    "Centar.mk": "Tabloidi",
    "NetPress.mk": "glavni",
}
DEFAULT_SOURCE_CATEGORY = "Lokalni"

# ── Ingestion Quality Settings ──────────────────────────────────
JUNK_KEYWORDS = [
    "horoskop",
    "vremenska prognoza",
    "vic dana",
    "na današnji dan",
    "dnevni meni",
    "recept dana",
    "kursna lista",
    "loto rezultati",
    "izvukli smo srećnog dobitnika",
    "zvezde im obećavaju",
    "horoskopski znaci",
    "nedeljni horoskop",
    "dnevni horoskop",
    "mesečni horoskop",
    "izvlačenje loto",
    "nagradne igre",
    "šta kažu zvezde",
    "zvezde predviđaju",
    "novac i prosperitet",
    "srećni datumi",
    "tiktok",
    "influenser",
    "lifestyle",
    "zabava",
    "kako da",
    "fitnes",
    "moda",
    "lepota",
    "trening",
    "putovanje",
]

# ── Balanced Coverage Settings ──────────────────────────────────
BALANCED_COVERAGE_THRESHOLD = 3  # clusters with 3+ diverse sources get a badge

# ── Performance & Resource Management ───────────────────────────
# Local model tasks can take significant RAM and can slow down the server.
# Set to False to disable local translation/style normalization.
LOCAL_TRANSLATION_ENABLED = os.environ.get("LOCAL_TRANSLATION_ENABLED", "true").lower() == "true"
ENABLE_EXPENSIVE_STYLE_TASKS = os.environ.get("ENABLE_EXPENSIVE_STYLE_TASKS", "false").lower() == "true"

# GPU acceleration for embeddings
ENABLE_GPU_ACCELERATION = os.environ.get("ENABLE_GPU_ACCELERATION", "false").lower() == "true"

# Database read replica configuration
DATABASE_READ_REPLICA_URL = os.environ.get("DATABASE_READ_REPLICA_URL", "")
USE_READ_REPLICA = bool(DATABASE_READ_REPLICA_URL)


def resolve_primary_database_url() -> str:
    """Return the primary write DATABASE_URL, rejecting accidental replica overrides."""
    url = (os.environ.get("DATABASE_URL") or "postgresql://localhost/presek").strip()
    replica_url = (DATABASE_READ_REPLICA_URL or os.environ.get("DATABASE_REPLICA_URL") or "").strip()
    if replica_url and url == replica_url:
        log = __import__("logging").getLogger("presek.config")
        log.critical(
            "DATABASE_URL points at the read replica (%s). "
            "Use DATABASE_READ_REPLICA_URL for reads and keep DATABASE_URL on the primary.",
            url,
        )
    lowered = url.lower()
    if "presek_replica" in lowered and (not replica_url or replica_url != url):
        log = __import__("logging").getLogger("presek.config")
        log.critical(
            "DATABASE_URL appears to target presek_replica (%s). Writes must use the primary database.",
            url,
        )
    return url


# ── AI Routing Configuration ────────────────────────────────────
# NOTE: mistral/mistral2 are intentionally omitted — their free tier returned
# `x-ratelimit-limit-req-minute: 0` (no usable quota) in Sep 2026, so they only
# wasted cascade round-trips. PROVIDERS still defines them for manual override.
PROVIDER_FALLBACK_ORDER_RESEARCH = ["gemini3", "gemini2", "gemini", "groq", "nvidia", "openrouter", "local"]
PROVIDER_FALLBACK_ORDER_SUMMARY = ["gemini3", "gemini2", "gemini", "groq", "nvidia", "openrouter", "local"]
PROVIDER_FALLBACK_ORDER = ["gemini3", "gemini2", "gemini", "groq", "nvidia", "openrouter", "local"]  # default

# Providers reserved exclusively for synthesis tasks.
# When set, these providers are excluded from summarize/research/default cascades
# so their rate-limit quota is preserved for higher-value synthesis calls.
# Comma-separated list, e.g. "gemini" or "gemini,nvidia".
PROVIDER_RESERVE_FOR_SYNTHESIS = [
    p.strip() for p in os.environ.get("PROVIDER_RESERVE_FOR_SYNTHESIS", "").split(",") if p.strip()
]

# ── Clustering Parameters ───────────────────────────────────────
CLUSTERING_THRESHOLDS = {
    "SIMILARITY_THRESHOLD": 0.45,
    "VECTOR_THRESHOLD": 0.28,
    "MAX_CLUSTER_SIZE": 35,
}

# ── History Context Parameters ──────────────────────────────────
HISTORY_SEMANTIC_THRESHOLD = 0.40
