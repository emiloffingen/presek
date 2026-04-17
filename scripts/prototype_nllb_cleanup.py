
import asyncio
import logging
import re
from database import db_manager as db
from nllb_translate import translate as nllb_translate
from ai_engine import rewrite_to_macedonian_locally

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.nllb_prototype")

async def standardize_text_nllb(text: str) -> str:
    """
    Experimental 'Style Normalization' using NLLB Round-trip.
    MK (Source) -> EN (Semantic Bridge) -> MK (Literary Standard)
    This often strips sensationalism and corrects dialect/slang.
    """
    if not text or len(text) < 20:
        return text

    try:
        # Step 1: Translate to English to capture core meaning (Semantic Bridge)
        # NLLB code for English is usually 'eng_Latn', Macedonian is 'mkd_Cyrl'
        # Our nllb_translate wrapper handles the mapping.
        english_bridge = nllb_translate(text, src_lang="mk", target_lang="en")
        if not english_bridge or english_bridge.strip().lower() == text.strip().lower():
            return text

        # Step 2: Translate back to Macedonian
        # The 'back-translation' forces the model to use its most 'canonical' Macedonian patterns.
        standardized = nllb_translate(english_bridge, src_lang="en", target_lang="mk")
        
        if not standardized or len(standardized) < 10:
            return text

        # Step 3: Final local Polish (Grammar/Stopwords)
        final = rewrite_to_macedonian_locally(standardized)
        return final
    except Exception as e:
        log.warning(f"Normalization failed: {e}")
        return text

async def run_prototype(limit=5):
    print("\n--- Presek NLLB Style Normalization Prototype ---")
    print(f"Goal: Use NLLB 'Back-Translation' to standardize news headlines.\n")

    # Pick 5 recent articles, ideally from diverse sources
    rows = db.execute(
        "SELECT id, source, title FROM articles WHERE created_at >= NOW() - INTERVAL '48 hours' LIMIT %s", 
        (limit,)
    )

    if not rows:
        print("No recent articles found to test.")
        return

    for row in rows:
        original = row['title']
        print(f"[{row['source']}] Original: {original}")
        
        # Run normalization
        standardized = await standardize_text_nllb(original)
        
        if standardized.strip().lower() != original.strip().lower():
            print(f" ✨ Standardized: {standardized}")
        else:
            print(" . (No changes needed/detected)")
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(run_prototype())
