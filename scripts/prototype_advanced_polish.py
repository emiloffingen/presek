
import asyncio
import logging
from database import db_manager as db
from nllb_translate import translate as nllb_translate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.advanced_polish")

async def run_polish_prototype(limit=5):
    print("\n--- Presek Advanced Linguistic Polish Prototype (NLLB 2.0) ---")
    print("Goal: Use MK -> EN -> MK round-trip to standardize news headlines.\n")

    # Target sources that often have less formal headlines
    rows = db.execute(
        """SELECT a.id, a.source, a.title FROM articles a
           JOIN sources s ON a.source = s.name
           WHERE s.credibility < 1.1
           AND a.created_at >= NOW() - INTERVAL '48 hours'
           LIMIT %s""", 
        (limit,)
    )

    if not rows:
        print("No suitable articles found. Testing with general recent articles...")
        rows = db.execute("SELECT id, source, title FROM articles ORDER BY created_at DESC LIMIT %s", (limit,))

    for row in rows:
        original = row['title']
        print(f"[{row['source']}]")
        print(f"  🔴 Original: {original}")
        
        # Step 1: MK -> EN
        en_bridge = nllb_translate(original, src_lang="mk", target_lang="en")
        
        # Step 2: EN -> MK (Back to standardized Macedonian)
        if en_bridge:
            polished = nllb_translate(en_bridge, src_lang="en", target_lang="mk")
            
            if polished and polished.strip().lower() != original.strip().lower():
                print(f"  ✨ Polished: {polished}")
            else:
                print("  ⚪ No significant change detected.")
        else:
            print("  ❌ Bridge failed.")
            
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(run_polish_prototype())
