from database import db_manager as db
import logging

log = logging.getLogger("presek")

def get_source_catalog():
    try:
        rows = db.execute("SELECT name, url FROM feed_sources WHERE is_active = TRUE")
        return [(r["name"], r["url"]) for r in rows]
    except Exception as e:
        log.warning(f"Failed to fetch feed sources from DB: {e}")
        return []

# For backward compatibility during transition, fetch at runtime when accessed if possible.
# Some scripts might still expect DEFAULT_SOURCE_CATALOG as a list.
DEFAULT_SOURCE_CATALOG = get_source_catalog()
