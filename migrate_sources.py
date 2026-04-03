
import os
import sys
from database import db_manager as db, init_db
import config

def migrate():
    print("Verifying schema...")
    init_db()
    
    # 1. Migrate RSS_FEEDS (Macedonian)
    print("Migrating RSS_FEEDS...")
    for entry in config.RSS_FEEDS:
        name = entry[0]
        url = entry[1]
        country = entry[2] if len(entry) > 2 else "🇲🇰"
        
        category = config.SOURCE_CATEGORIES.get(name, config.DEFAULT_SOURCE_CATEGORY)
        credibility = config.SOURCE_CREDIBILITY.get(name, config.DEFAULT_CREDIBILITY)
        limit = config.SOURCE_LIMITS.get(name, 10)
        
        sql = """
            INSERT INTO sources (name, url, country, category, credibility, source_limit)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                url = EXCLUDED.url,
                country = EXCLUDED.country,
                category = EXCLUDED.category,
                credibility = EXCLUDED.credibility,
                source_limit = EXCLUDED.source_limit
        """
        db.execute(sql, (name, url, country, category, credibility, limit), fetch=False)
        print(f"  + {name}")

    # 2. Migrate DIASPORA_FEEDS
    print("Migrating DIASPORA_FEEDS...")
    for entry in config.DIASPORA_FEEDS:
        name = entry[0]
        url = entry[1]
        country = entry[2] if len(entry) > 2 else "Свет"
        
        category = "Меѓународни" # Default for diaspora
        if name in config.SOURCE_CATEGORIES:
            category = config.SOURCE_CATEGORIES[name]
            
        credibility = config.SOURCE_CREDIBILITY.get(name, config.DEFAULT_CREDIBILITY)
        limit = config.SOURCE_LIMITS.get(name, 10)
        
        sql = """
            INSERT INTO sources (name, url, country, category, credibility, source_limit)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                url = EXCLUDED.url,
                country = EXCLUDED.country,
                category = EXCLUDED.category,
                credibility = EXCLUDED.credibility,
                source_limit = EXCLUDED.source_limit
        """
        db.execute(sql, (name, url, country, category, credibility, limit), fetch=False)
        print(f"  + {name}")

    print("Migration complete!")

if __name__ == "__main__":
    migrate()
