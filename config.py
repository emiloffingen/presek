import os
import logging

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # Optional in pre-provisioned environments.

    def load_dotenv():
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
    "PRESEK_ADMIN_TOKEN",
    "NTFY_TOPIC",
    "NTFY_TOKEN",
    "VAPID_PRIVATE_KEY",
    "VAPID_PUBLIC_KEY",
    "SMTP_HOST",
    "SMTP_PASS",
)

# Keys that should NEVER be used without explicit configuration
SENSITIVE_ENV_KEYS = (
    "DATABASE_URL",
    "REDIS_URL",
    "SECRET_KEY",
    "PRESEK_ADMIN_TOKEN",
    "SMTP_PASS",
    "CLOUDFLARE_API_TOKEN",
    "R2_SECRET_ACCESS_KEY",
    "POLLINATIONS_API_KEY",
    "VAPID_PRIVATE_KEY",
    "CF_AI_GATEWAY_TOKEN",
)


def validate_required_env(required_keys=REQUIRED_RUNTIME_ENV_KEYS):
    """Validate that critical environment variables are set before serving traffic."""
    missing = [k for k in required_keys if not os.environ.get(k)]
    if missing:
        # In production, this should be a hard failure
        if os.environ.get("ENV") == "production":
            missing_str = ", ".join(missing)
            log.critical(
                f"PRODUCTION STARTUP FAILED: Missing required environment variables: {missing_str}"
            )
            raise RuntimeError(f"Missing required environment variables: {missing_str}")
        else:
            # In development, log warnings but allow startup
            for key in missing:
                log.warning(
                    f"Missing environment variable (required for production): {key}"
                )
            log.warning(
                f"Running in development mode with missing config. For production, set: {', '.join(missing)}"
            )


def validate_recommended_env():
    """Warn about missing recommended configuration."""
    missing = [k for k in RECOMMENDED_ENV_KEYS if not os.environ.get(k)]
    if missing:
        for key in missing:
            log.warning(f"Recommended environment variable not set: {key}")


def check_sensitive_values():
    """Warn if sensitive environment variables contain default/test values."""
    dangerous_patterns = [
        ("DATABASE_URL", ["password", "1234", "test", "changeme", "postgres://"]),
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
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS = {"sub": "mailto:admin@presek.live"}
PRESEK_ADMIN_TOKEN = os.environ.get("PRESEK_ADMIN_TOKEN", "")

# ── Additional AI Providers (Gemini) ───────────────────────────
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODELS = [
    model.strip()
    for model in os.environ.get(
        "GEMINI_FALLBACK_MODELS",
        "gemini-2.5-flash,gemini-2.5-pro",
    ).split(",")
    if model.strip()
]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

REFRESH_INTERVAL = 300
FEED_LIMIT = 10
AI_DAILY_LIMIT = 1000000
CLUSTER_LOOKBACK = 300  # Narrowed to reduce memory pressure
BREAKING_SCORE_THRESHOLD = 4.5
DB_RETAIN_DAYS = 180  # articles older than this are pruned daily
DB_RETAIN_FAILED_TASKS_DAYS = 360  # failed tasks older than this are pruned daily

# ── Auto-summarization settings ──────────────────────────────────
AUTO_SUMMARIZE_TOP_N = 15  # summarize the top N clusters each cycle
AUTO_SUMMARIZE_MIN_SRC = 2  # only clusters with 2+ sources get synthesis
AUTO_SUMMARIZE_DELAY = 1.5  # seconds between API calls (rate limit protection)

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
        "Nova.rs",
        "Danas",
        "RTS",
        "Vreme",
        "B92",
        "Mondo",
        "Politika",
        "Novosti",
        "021",
        "Srbija Danas",
        "Republika",
        "NIN",
        "Nedeljnik",
        "Euronews Srbija",
        "021.rs",
        "Insajder",
        "KRIK"
    }
)

DIASPORA_FEEDS = []

SOURCE_CREDIBILITY = {
    # SR sources
    "N1 Info": 1.9,
    "Nova.rs": 1.8,
    "Danas": 1.9,
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
    "Srbija Danas": 0.9,
    "Republika": 0.8,
    "Mondo": 1.2,
    "Novosti": 1.4,
}
DEFAULT_CREDIBILITY = 0.8

SOURCE_CATEGORIES = {
    "N1 Info": "Nezavisni",
    "Nova.rs": "Nezavisni",
    "Danas": "Nezavisni",
    "RTS": "Javni Servis",
    "Vreme": "Istraživački",
    "NIN": "Istraživački",
    "Nedeljnik": "Istraživački",
    "Politika": "Glavni",
    "B92": "Glavni",
    "Blic": "Glavni",
    "Euronews Srbija": "Glavni",
    "Insajder": "Istraživački",
    "KRIK": "Istraživački",
    "Telegraf": "Tabloidi",
    "Kurir": "Tabloidi",
    "Alo": "Tabloidi",
    "Informer": "Tabloidi",
    "Srbija Danas": "Tabloidi",
    "Republika": "Tabloidi",
    "Mondo": "Glavni",
    "Novosti": "Glavni",
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

# ── Image Generation Configuration ──────────────────────────────
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")

# ── Performance & Resource Management ───────────────────────────
# Large models (Gemma 2 2B) take significant RAM and can slow down the server.
# Set to False to disable local translation/style normalization.
LOCAL_TRANSLATION_ENABLED = (
    os.environ.get("LOCAL_TRANSLATION_ENABLED", "true").lower() == "true"
)
ENABLE_EXPENSIVE_STYLE_TASKS = (
    os.environ.get("ENABLE_EXPENSIVE_STYLE_TASKS", "false").lower() == "true"
)

# ── AI Routing Configuration ────────────────────────────────────
# Use Mistral large (free) first, then small (paid)
PROVIDER_FALLBACK_ORDER_RESEARCH = ["mistral_large", "gemini", "mistral_small"]
PROVIDER_FALLBACK_ORDER_SUMMARY = ["mistral_large", "gemini", "mistral_small"]
PROVIDER_FALLBACK_ORDER = [
    "mistral_large",
    "gemini",
    "mistral_small",
]  # default

# ── Clustering Parameters ───────────────────────────────────────
CLUSTERING_THRESHOLDS = {
    "SIMILARITY_THRESHOLD": 0.45,
    "VECTOR_THRESHOLD": 0.28,
    "MAX_CLUSTER_SIZE": 35,
}
