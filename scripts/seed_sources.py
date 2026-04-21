
from database import db_manager as db
from source_catalog import DEFAULT_SOURCE_CATALOG

def seed_sources():
    print(f"Seeding {len(DEFAULT_SOURCE_CATALOG)} sources from source_catalog.py...")
    for name, url in DEFAULT_SOURCE_CATALOG:
        # Check if source already exists
        exists = db.execute_one("SELECT name FROM sources WHERE name = %s", (name,))
        if not exists:
            db.execute(
                "INSERT INTO sources (name, url, is_active) VALUES (%s, %s, %s)",
                (name, url, True),
                fetch=False
            )
            print(f"  + Added {name}")
        else:
            print(f"  . {name} already exists")
    print("Seeding complete.")

if __name__ == "__main__":
    seed_sources()
