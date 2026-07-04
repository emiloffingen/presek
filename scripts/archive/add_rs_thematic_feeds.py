"""Add and recategorize RS thematic RSS feeds for tech, economy, health, and sport."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import db_manager as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("presek.add_rs_thematic_feeds")

CATEGORY_UPDATES = {
    "Biznis.rs": "Biznis",
    "Nova Ekonomija": "Ekonomija",
    "Danas - Ekonomija": "Ekonomija",
    "Benchmark": "Tehnologija",
    "BenchMark": "Tehnologija",
    "PC Press": "Tehnologija",
    "Netokracija": "Tehnologija",
    "eKlinika": "Zdravlje",
    "Balkanrock": "Kultura",
    "Danas - Kultura": "Kultura",
    "Kurir Sport": "Sport",
    "HotSport": "Sport",
    "Sportski žurnal": "Sport",
    "MaxBet Sport": "Sport",
}

URL_UPDATES = {
    "Nova Ekonomija": "https://novaekonomija.rs/feed/",
}

DEACTIVATE = [
    "BIRN",
    "Kosovo Online",
    "MedicinskiPregled.rs",
    "BenchMark",
]

NEW_FEEDS = [
    {
        "name": "N1 Biznis",
        "url": "https://n1info.rs/biznis/feed/",
        "country": "RS",
        "category": "Ekonomija",
        "language": "sr",
        "credibility": 0.90,
    },
    {
        "name": "Blic - Ekonomija",
        "url": "https://www.blic.rs/rss/ekonomija",
        "country": "RS",
        "category": "Ekonomija",
        "language": "sr",
        "credibility": 0.85,
    },
    {
        "name": "Zdravlje-info.rs",
        "url": "https://www.zdravlje-info.rs/feed/",
        "country": "RS",
        "category": "Zdravlje",
        "language": "sr",
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


def add_rs_thematic_feeds(*, dry_run: bool = True) -> None:
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

    for name in DEACTIVATE:
        log.info("Deactivate %s", name)
        if not dry_run:
            db.execute("UPDATE sources SET is_active = FALSE WHERE name = %s", (name,), fetch=False)
            db.execute("UPDATE feed_sources SET is_active = FALSE WHERE name = %s", (name,), fetch=False)

    for feed in NEW_FEEDS:
        _upsert_feed(feed, dry_run=dry_run)

    log.info("RS thematic feed update completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add/recategorize RS thematic RSS feeds")
    parser.add_argument("--commit", action="store_true", help="Apply changes to the database")
    args = parser.parse_args()
    add_rs_thematic_feeds(dry_run=not args.commit)
