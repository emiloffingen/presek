
import asyncio
import logging
from database import db_manager as db
from nllb_translate import translate as nllb_translate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.multilang_prototype")

async def run_multilang_prototype(limit=3):
    print("\n--- Presek Multi-language Prototype (EN & SQ) ---")
    
    rows = db.execute(
        "SELECT source, title FROM articles WHERE created_at >= NOW() - INTERVAL '48 hours' LIMIT %s", 
        (limit,)
    )

    if not rows:
        print("No recent articles found.")
        return

    for row in rows:
        original = row['title']
        print(f"[{row['source']}]")
        print(f"  MK: {original}")
        
        # 1. Test MK -> EN
        en_version = nllb_translate(original, src_lang="mk", target_lang="en")
        print(f"  EN: {en_version}")

        # 2. Test MK -> EN -> SQ (Semantic Bridge)
        if en_version:
            sq_version = nllb_translate(en_version, src_lang="en", target_lang="sq")
            print(f"  SQ: {sq_version}")
        else:
            print("  SQ: (Skipped, EN bridge failed)")
            
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(run_multilang_prototype())
