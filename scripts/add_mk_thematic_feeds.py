"""Add and recategorize MK thematic RSS feeds for tech, economy, and health coverage."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import db_manager as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("presek.add_mk_thematic_feeds")

CATEGORY_UPDATES = {
    "ИТ.мк": "Tehnologija",
    "СмартПортал.мк": "Tehnologija",
    "БизнисВести.мк": "Biznis",
    "Бизнис Инфо": "Biznis",
    "Иновативност": "Biznis",
    "Денар": "Biznis",
    "Денар.мк": "Biznis",
    "Фактор.мк": "Biznis",
}

URL_UPDATES = {
    "Макфакс": "https://makfax.com.mk/rss/",
}

REACTIVATE = [
    "Фактор.мк",
]

NEW_FEEDS = [
    {
        "name": "Економски.мк",
        "url": "https://ekonomski.mk/feed/",
        "country": "MK",
        "category": "Ekonomija",
        "language": "mk",
        "credibility": 0.85,
    },
    {
        "name": "Лекаринфо.мк",
        "url": "https://lekarinfo.mk/feed/",
        "country": "MK",
        "category": "Zdravje",
        "language": "mk",
        "credibility": 0.80,
    },
]


def _upsert_feed(feed: dict, *, dry_run: bool) -> None:
    name = feed["name"]
    url = feed["url"]
    category = feed["category"]
    country = feed["country"]
    language = feed["language"]
    credibility = feed["credibility"]

    log.info("Add feed: %s (%s)", name, url)
    if dry_run:
        return

    if not db.execute_one("SELECT name FROM sources WHERE name = %s", (name,)):
        db.execute(
            """
            INSERT INTO sources (name, url, country, category, language, credibility, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            (name, url, country, category, language, credibility),
            fetch=False,
        )
    else:
        db.execute(
            """
            UPDATE sources
            SET url = %s, country = %s, category = %s, language = %s, credibility = %s,
                is_active = TRUE, pause_mode = NULL
            WHERE name = %s
            """,
            (url, country, category, language, credibility, name),
            fetch=False,
        )

    if not db.execute_one("SELECT name FROM feed_sources WHERE name = %s", (name,)):
        db.execute(
            "INSERT INTO feed_sources (name, url, category, is_active) VALUES (%s, %s, %s, TRUE)",
            (name, url, category),
            fetch=False,
        )
    else:
        db.execute(
            """
            UPDATE feed_sources
            SET url = %s, category = %s, is_active = TRUE, pause_mode = NULL
            WHERE name = %s
            """,
            (url, category, name),
            fetch=False,
        )


def add_mk_thematic_feeds(*, dry_run: bool = True) -> None:
    if dry_run:
        log.info("DRY RUN: no database changes will be committed")

    for name, category in CATEGORY_UPDATES.items():
        log.info("Recategorize %s -> %s", name, category)
        if not dry_run:
            db.execute(
                "UPDATE sources SET category = %s WHERE name = %s",
                (category, name),
                fetch=False,
            )
            db.execute(
                "UPDATE feed_sources SET category = %s WHERE name = %s",
                (category, name),
                fetch=False,
            )

    for name, url in URL_UPDATES.items():
        log.info("Update URL %s -> %s", name, url)
        if not dry_run:
            db.execute("UPDATE sources SET url = %s WHERE name = %s", (url, name), fetch=False)
            db.execute("UPDATE feed_sources SET url = %s WHERE name = %s", (url, name), fetch=False)

    for name in REACTIVATE:
        log.info("Reactivate %s", name)
        if not dry_run:
            db.execute(
                "UPDATE sources SET is_active = TRUE, pause_mode = NULL WHERE name = %s",
                (name,),
                fetch=False,
            )
            db.execute(
                "UPDATE feed_sources SET is_active = TRUE, pause_mode = NULL WHERE name = %s",
                (name,),
                fetch=False,
            )

    for feed in NEW_FEEDS:
        _upsert_feed(feed, dry_run=dry_run)

    log.info("MK thematic feed update completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add/recategorize MK thematic RSS feeds")
    parser.add_argument("--commit", action="store_true", help="Apply changes to the database")
    args = parser.parse_args()
    add_mk_thematic_feeds(dry_run=not args.commit)
