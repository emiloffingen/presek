import time
import logging
from trending import get_trending
from app import set_cache

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("trending_backfill")

def backfill():
    log.info("Recalculating and caching trending topics...")
    try:
        # get_trending no longer needs a path after Postgres migration
        results = get_trending()
        if results:
            set_cache("trending", results, ttl=900)
            log.info(f"Successfully cached {len(results)} trending topics.")
        else:
            log.warning("No trending topics found to cache.")
    except Exception as e:
        log.error(f"An error occurred during trending backfill: {e}")

if __name__ == "__main__":
    while True:
        backfill()
        log.info("Sleeping for 15 minutes...")
        time.sleep(900)
