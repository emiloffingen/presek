
import os
import sys
from database import db_manager as db
from config import RSS_FEEDS

def seed_sources():
    print(f"Seeding {len(RSS_FEEDS)} sources from config.py...")
    for name, url in RSS_FEEDS:
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
