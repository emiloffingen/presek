"""
translate_existing.py — Backfill translations for articles where it failed.
"""
import sqlite3
import os
import sys
import time

# Ensure we can import from app.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import translate_titles_batch, DB_PATH, normalize_headline

def backfill():
    print(f"--- Starting translation backfill using DB: {DB_PATH} ---", flush=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Fetch articles from foreign sources where title is same as original_title
    # and country is NOT Macedonia.
    rows = conn.execute(
        "SELECT id, title, original_title, source FROM articles WHERE country != '🇲🇰' AND title = original_title"
    ).fetchall()
    
    if not rows:
        print("No untranslated foreign articles found.", flush=True)
        conn.close()
        return

    print(f"Found {len(rows)} articles to translate.", flush=True)
    
    # Process in batches of 10
    BATCH_SIZE = 10
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        titles_to_translate = [r["original_title"] for r in batch]
        
        print(f"Translating batch {i//BATCH_SIZE + 1}/{(len(rows)-1)//BATCH_SIZE + 1}...", flush=True)
        
        try:
            translated = translate_titles_batch(titles_to_translate)
            
            # Update DB
            update_count = 0
            for idx, row_data in enumerate(batch):
                new_title = translated[idx]
                if new_title and new_title != row_data["original_title"]:
                    new_title = normalize_headline(new_title)
                    conn.execute(
                        "UPDATE articles SET title = ? WHERE id = ?",
                        (new_title, row_data["id"])
                    )
                    update_count += 1
            
            conn.commit()
            print(f"  Updated {update_count} articles in this batch.", flush=True)
        except Exception as e:
            print(f"  Error in batch {i//BATCH_SIZE + 1}: {e}", flush=True)
        
        # Small delay between batches beyond what's inside translate_titles_batch
        time.sleep(2)

    print("Backfill complete.", flush=True)
    conn.close()

if __name__ == "__main__":
    # Check for GOOGLE_API_KEY
    if not os.environ.get("GOOGLE_API_KEY"):
        # Try to load from .env
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("GOOGLE_API_KEY="):
                        os.environ["GOOGLE_API_KEY"] = line.split("=")[1].strip()
                        break
    
    if not os.environ.get("GOOGLE_API_KEY"):
        print("Error: GOOGLE_API_KEY not found in environment or .env file.", flush=True)
        sys.exit(1)
        
    backfill()
