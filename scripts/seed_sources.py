from database import db_manager as db
from source_catalog import DEFAULT_SOURCE_CATALOG
from config import (
    SOURCE_CREDIBILITY,
    SOURCE_CATEGORIES,
    SOURCE_LIMITS,
    DEFAULT_CREDIBILITY,
    DEFAULT_SOURCE_CATEGORY,
)


def seed_sources():
    print(
        f"Syncing {len(DEFAULT_SOURCE_CATALOG)} sources from source_catalog.py with metadata from config.py..."
    )
    for name, url in DEFAULT_SOURCE_CATALOG:
        cred = SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY)
        cat = SOURCE_CATEGORIES.get(name, DEFAULT_SOURCE_CATEGORY)
        limit = SOURCE_LIMITS.get(name)

        # Check if source already exists
        exists = db.execute_one("SELECT name FROM sources WHERE name = %s", (name,))
        if not exists:
            db.execute(
                "INSERT INTO sources (name, url, category, credibility, source_limit, is_active) VALUES (%s, %s, %s, %s, %s, %s)",
                (name, url, cat, cred, limit, True),
                fetch=False,
            )
            print(f"  + Added {name} (Cred: {cred}, Cat: {cat})")
        else:
            # Update existing source with latest metadata from config if needed
            db.execute(
                "UPDATE sources SET url=%s, category=%s, credibility=%s, source_limit=%s WHERE name=%s",
                (url, cat, cred, limit, name),
                fetch=False,
            )
            print(f"  . Updated {name}")
    print("Sync complete.")


if __name__ == "__main__":
    seed_sources()
