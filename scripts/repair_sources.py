import argparse
import asyncio
import logging

from core.database import db_manager as db

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("presek.repair_sources")

# Sources to update (404s with known new endpoints)
REPLACEMENTS = {
    "CrnoBelo": "https://www.crnobelo.com/feed",
    "MKD.mk": "https://mkd.mk/feed/",
    "Vesti.mk": "https://vesti.mk/feed",
    "Sputnjik Srbija": "https://sputnikportal.rs/export/rss2/archive/index.xml",  # Common sputnik fallback
    "SakamDaKazam.mk": "https://sdk.mk/feed/",
    "KumanovoNews": "https://kumanovonews.mk/feed/",
    "Kurir Sport": "https://www.kurir.rs/rss/sport/",
    "InfoKG": "https://infokg.rs/rss",
    "Tocka.mk": "https://tocka.com.mk/rss",
}

# Sources to deactivate (persistent DNS errors or dead domains)
DEACTIVATE = [
    "Basket.mk",
    "Prilep.mk",
    "Fudbal.mk",
    "Pres24.mk",
    "StrumicaNet",
    "Dnevnik.mk",
    "MkdNews.mk",
    "MkdSport.mk",
    "BeliMuabeti.mk",
    "Utrinski.mk",
    "BalkanSport.mk",
    "Vesti-MK",
]


async def repair_sources(dry_run=True):
    if dry_run:
        log.info("DRY RUN: No changes will be committed to the database.")

    # 1. Apply replacements
    for name, new_url in REPLACEMENTS.items():
        log.info(f"Checking replacement for {name} -> {new_url}")
        if not dry_run:
            await db.async_execute(
                "UPDATE feed_sources SET url = %s, is_active = TRUE WHERE name = %s", (new_url, name), fetch=False
            )
            log.info(f"Updated {name}")

    # 2. Deactivate dead sources
    for name in DEACTIVATE:
        log.info(f"Deactivating source: {name}")
        if not dry_run:
            await db.async_execute("UPDATE feed_sources SET is_active = FALSE WHERE name = %s", (name,), fetch=False)
            log.info(f"Deactivated {name}")

    log.info("Repair process completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair broken news sources in the database.")
    parser.add_argument("--commit", action="store_true", help="Commit changes to the database (defaults to dry run)")
    args = parser.parse_args()

    asyncio.run(repair_sources(dry_run=not args.commit))
