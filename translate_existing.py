import database
import time
import logging
from database import get_db
from ai_engine import translate_to_macedonian

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("translate_existing")

def translate_batch():
    conn = get_db()
    # Find untranslated international articles
    rows = conn.execute(
        "SELECT id, title, description, country FROM articles WHERE country != '🇲🇰' AND is_translated = 0 LIMIT 50"
    ).fetchall()
    
    if not rows:
        print("No more articles to translate.")
        conn.close()
        return False

    print(f"Translating batch of {len(rows)} articles...")
    
    for r in rows:
        aid, title, desc, country = r['id'], r['title'], r['description'], r['country']
        
        translated_title = translate_to_macedonian(title)
        time.sleep(0.5) # Rate limit protection for Cloudflare
        
        translated_desc = translate_to_macedonian(desc) if desc else ""
        time.sleep(0.5)
        
        if translated_title:
            conn.execute(
                "UPDATE articles SET title = %s, original_title = %s, description = %s, original_description = %s, is_translated = 1 WHERE id = %s",
                (translated_title, title, translated_desc or desc, desc, aid)
            )
            print(f"✓ Translated: {translated_title[:50]}...")
        else:
            log.warning(f"✗ Failed: {title[:50]}")
            print(f"✗ Failed: {title[:50]}...")
            
        conn.commit()
    
    conn.close()
    return True

if __name__ == "__main__":
    # We can run a few batches
    for _ in range(5):
        if not translate_batch():
            break
        time.sleep(2)
