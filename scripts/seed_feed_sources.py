from database import db_manager as db

# Serbian News Catalog
SERBIAN_FEED_CATALOG = [
    ("Blic", "https://www.blic.rs/rss/danasnje-vesti"),
    ("N1 Info", "https://n1info.rs/feed/"),
    ("Nova.rs", "https://nova.rs/feed/"),
    ("Danas", "https://www.danas.rs/feed/"),
    ("RTS", "https://www.rts.rs/page/stories/sr/rss.html"),
    ("B92", "https://www.b92.net/info/rss/vesti.xml"),
    ("Kurir", "https://www.kurir.rs/rss/"),
    ("Telegraf", "https://www.telegraf.rs/rss"),
    ("Politika", "https://www.politika.rs/rss/"),
    ("Novosti", "https://www.novosti.rs/rss"),
    ("Informer", "https://informer.rs/rss/vesti/sve"),
    ("Alo", "https://www.alo.rs/rss/sve-vesti"),
    ("Mondo", "https://mondo.rs/rss/1/Sve-vesti"),
    ("021.rs", "https://www.021.rs/rss/Sve-vesti"),
    ("Srbija Danas", "https://www.srbijadanas.com/rss/sve-vesti"),
    ("Republika", "https://www.republika.rs/rss/sve-vesti"),
    ("Vreme", "https://www.vreme.com/feed/"),
    ("NIN", "https://www.nin.rs/rss"),
    ("Nedeljnik", "https://www.nedeljnik.rs/feed/"),
    ("Insajder", "https://insajder.net/rss/vesti"),
    ("KRIK", "https://www.krik.rs/feed/"),
]

def seed_feed_sources():
    print(f"Seeding {len(SERBIAN_FEED_CATALOG)} Serbian feed sources into the 'feed_sources' table...")
    
    added = 0
    updated = 0
    
    for name, url in SERBIAN_FEED_CATALOG:
        exists = db.execute_one("SELECT name FROM feed_sources WHERE name = %s", (name,))
        if not exists:
            db.execute(
                "INSERT INTO feed_sources (name, url, is_active) VALUES (%s, %s, %s)",
                (name, url, True),
                fetch=False,
            )
            added += 1
            print(f"  + Added feed source: {name}")
        else:
            db.execute(
                "UPDATE feed_sources SET url = %s WHERE name = %s",
                (url, name),
                fetch=False,
            )
            updated += 1
            print(f"  . Updated feed source: {name}")
            
    print(f"Sync complete. Added {added}, updated {updated} feed sources.")

if __name__ == "__main__":
    seed_feed_sources()
