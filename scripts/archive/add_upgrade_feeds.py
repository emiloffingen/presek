import os
import sys

# Ensure project root in path
sys.path.append(os.getcwd())

from core.database import db_manager as db

NEW_FEEDS = [
    {
        "name": "PharmaMedica",
        "url": "https://pharmamedica.rs/feed/",
        "country": "RS",
        "category": "Zdravlje",
        "language": "sr",
        "credibility": 0.85,
    },
    {
        "name": "eKlinika",
        "url": "https://eklinika.telegraf.rs/feed",
        "country": "RS",
        "category": "Zdravlje",
        "language": "sr",
        "credibility": 0.80,
    },
    {
        "name": "Nauka.mk",
        "url": "https://nauka.mk/feed/",
        "country": "MK",
        "category": "Zdravstvo",
        "language": "mk",
        "credibility": 0.85,
    },
    {
        "name": "CeSID",
        "url": "https://www.cesid.rs/feed/",
        "country": "RS",
        "category": "Politika",
        "language": "sr",
        "credibility": 0.90,
    },
    {
        "name": "Akademik",
        "url": "https://akademik.mk/feed/",
        "country": "MK",
        "category": "Politika",
        "language": "mk",
        "credibility": 0.85,
    },
    {
        "name": "Inovativnost",
        "url": "https://inovativnost.mk/feed/",
        "country": "MK",
        "category": "Biznis",
        "language": "mk",
        "credibility": 0.80,
    },
]


def add_feeds():
    print("Seeding upgraded category feeds into DB...")

    added_sources = 0
    added_feeds = 0

    for f in NEW_FEEDS:
        name = f["name"]
        url = f["url"]
        country = f["country"]
        category = f["category"]
        language = f["language"]
        credibility = f["credibility"]

        # 1. Handle 'sources' table
        source_exists = db.execute_one("SELECT name FROM sources WHERE name = %s", (name,))
        if not source_exists:
            db.execute(
                """
                INSERT INTO sources (name, url, country, category, language, credibility, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                """,
                (name, url, country, category, language, credibility),
                fetch=False,
            )
            print(f"  + Added source metadata: {name} (Country: {country}, Cat: {category})")
            added_sources += 1
        else:
            db.execute(
                """
                UPDATE sources 
                SET url = %s, country = %s, category = %s, language = %s, credibility = %s, is_active = TRUE, pause_mode = NULL
                WHERE name = %s
                """,
                (url, country, category, language, credibility, name),
                fetch=False,
            )
            print(f"  . Updated source metadata: {name}")

        # 2. Handle 'feed_sources' table
        feed_exists = db.execute_one("SELECT name FROM feed_sources WHERE name = %s", (name,))
        if not feed_exists:
            db.execute(
                """
                INSERT INTO feed_sources (name, url, category, is_active)
                VALUES (%s, %s, %s, TRUE)
                """,
                (name, url, category),
                fetch=False,
            )
            print(f"  + Added feed source: {name} ({url})")
            added_feeds += 1
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
            print(f"  . Updated feed source URL: {name}")

    print(f"Done! Seeded {added_sources} sources and {added_feeds} active feeds.")


if __name__ == "__main__":
    add_feeds()
