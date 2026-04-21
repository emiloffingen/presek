import logging
from database import db_manager as db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("reset_sources")

def reset():
    log.info("Resetting sources and forcing fresh fetch...")
    
    # 1. Re-activate all sources
    db.execute("UPDATE sources SET is_active = TRUE, pause_mode = NULL, pause_reason = NULL, last_fetched = NULL", fetch=False)
    
    # 2. Clear any lingering locks in Redis if possible (we'll just wait for TTL if not)
    log.info("Sources reset. Ingestion will pick up new items in the next cycle.")

if __name__ == "__main__":
    reset()
