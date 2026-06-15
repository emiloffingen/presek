import argparse
import asyncio
import logging

from core.database import db_manager as db

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("presek.repair_sources")

# Sources with verified working RSS endpoints
REPLACEMENTS = {
    "MKD.mk": "https://mkd.mk/feed/",
    "Vesti.mk": "https://vesti.mk/feed",
    "Sputnjik Srbija": "https://sputnikportal.rs/export/rss2/archive/index.xml",
    "SakamDaKazam.mk": "https://sdk.mk/index.php/mk/feed/",
    "KumanovoNews": "https://kumanovonews.mk/feed/",
    "Kurir Sport": "https://www.kurir.rs/rss/sport/",
    "InfoKG": "https://infokg.rs/rss",
    "Tocka.mk": "https://tocka.com.mk/rss",
    # MK feeds with broken or stale URLs
    "Infomax.mk": "https://infomax.mk/feed/",
    "Гол.мк": "https://gol.mk/rss.xml",
    # RS feeds with broken or stale URLs
    "Novosti": "https://www.novosti.rs/rss/danasnje-vesti",
    "Vlada.rs": "https://vlada.rs/rss/",
    "Danas - Ekonomija": "https://www.danas.rs/tag/ekonomija/feed/",
    "Danas - Kultura": "https://www.danas.rs/tag/kultura/feed/",
}

# Feeds that work but were accidentally deactivated in feed_sources
REACTIVATE = [
    "BIRN",
    "Kosovo Online",
    "Danas - Ekonomija",
    "Inpress.mk",
]

# Sources to deactivate (dead domains, no RSS, empty feeds, or wrong language)
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
    "Ekapija",
    # MK feeds with no working Macedonian RSS
    "CrnoBelo",
    "Алсат",
    "Portalb.mk",
    "Засе.мк",
    "Капитал",
    "Тајм.мк",
    "Радио Слободна Европа",
    # RS feeds with no working Serbian RSS
    "Srbija danas",
    "NIN",
    "Euronews Srbija",
    "Tanjug",
    "Tanjug Biznis",
    "Mozzart Sport",
    "Mondo",
    "ITVesti.rs",
    "Poljoprivrednik",
    "Subotica.com",
    "PharmaMedica",
    "Kamatica",
]


async def _update_url(name: str, new_url: str) -> None:
    await db.async_execute(
        "UPDATE feed_sources SET url = %s, is_active = TRUE, pause_mode = NULL WHERE name = %s",
        (new_url, name),
        fetch=False,
    )
    await db.async_execute(
        "UPDATE sources SET url = %s, is_active = TRUE, pause_mode = NULL WHERE name = %s",
        (new_url, name),
        fetch=False,
    )


async def _reactivate(name: str) -> None:
    await db.async_execute(
        "UPDATE feed_sources SET is_active = TRUE, pause_mode = NULL WHERE name = %s",
        (name,),
        fetch=False,
    )
    await db.async_execute(
        "UPDATE sources SET is_active = TRUE, pause_mode = NULL WHERE name = %s",
        (name,),
        fetch=False,
    )


async def _deactivate(name: str) -> None:
    await db.async_execute(
        "UPDATE feed_sources SET is_active = FALSE WHERE name = %s",
        (name,),
        fetch=False,
    )
    await db.async_execute(
        "UPDATE sources SET is_active = FALSE WHERE name = %s",
        (name,),
        fetch=False,
    )


async def repair_sources(dry_run=True):
    if dry_run:
        log.info("DRY RUN: No changes will be committed to the database.")

    for name, new_url in REPLACEMENTS.items():
        log.info("Replacement: %s -> %s", name, new_url)
        if not dry_run:
            await _update_url(name, new_url)
            log.info("Updated %s", name)

    for name in REACTIVATE:
        log.info("Reactivate: %s", name)
        if not dry_run:
            await _reactivate(name)
            log.info("Reactivated %s", name)

    for name in DEACTIVATE:
        log.info("Deactivate: %s", name)
        if not dry_run:
            await _deactivate(name)
            log.info("Deactivated %s", name)

    log.info("Repair process completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair broken news sources in the database.")
    parser.add_argument("--commit", action="store_true", help="Commit changes to the database (defaults to dry run)")
    args = parser.parse_args()

    asyncio.run(repair_sources(dry_run=not args.commit))
