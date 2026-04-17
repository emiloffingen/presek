
import asyncio
import logging
from database import db_manager as db
from nllb_translate import translate as nllb_translate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.albanian_prototype")

async def run_albanian_prototype(limit=5):
    print("\n--- Presek Albanian Translation Prototype (NLLB-200) ---")
    print(f"Goal: Translate Macedonian headlines into Albanian.\n")

    # Pick 5 recent articles
    rows = db.execute(
        "SELECT source, title FROM articles WHERE created_at >= NOW() - INTERVAL '48 hours' LIMIT %s", 
        (limit,)
    )

    if not rows:
        print("No recent articles found to test.")
        return

    for row in rows:
        original = row['title']
        print(f"[{row['source']}] MK: {original}")
        
        # Translate to Albanian
        # translate(text, src_lang, target_lang)
        translated = nllb_translate(original, src_lang="mk", target_lang="sq")
        
        if translated:
            print(f"         SQ: {translated}")
        else:
            print("         ❌ Translation failed.")
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(run_albanian_prototype())
