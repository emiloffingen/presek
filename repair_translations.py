import logging
import datetime
from tasks import translate_article_task
from database import get_db, load_env

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek_repair")

def repair_translations():
    load_env()
    conn = get_db()
    try:
        # Find untranslated diaspora articles
        rows = conn.execute("""
            SELECT id, title, description 
            FROM articles 
            WHERE is_translated = 0 AND country != '🇲🇰'
            ORDER BY created_at DESC
            LIMIT 200
        """).fetchall()
        
        if not rows:
            print("No untranslated diaspora articles found.")
            return
            
        print(f"Dispatching translation tasks for {len(rows)} articles...")
        for r in rows:
            translate_article_task.delay(r['id'], r['title'], r['description'])
            
        print("Tasks dispatched.")
    finally:
        conn.close()

if __name__ == "__main__":
    repair_translations()
