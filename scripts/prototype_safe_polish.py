
import asyncio
import logging
import re
from database import db_manager as db
from nllb_translate import translate as nllb_translate
from entities import extract_entities

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.safe_polish")

async def run_safe_polish_prototype(limit=5):
    print("\n--- Presek Entity-Safe Linguistic Polish Prototype (NLLB 2.0) ---")
    
    # Target some headlines
    rows = db.execute(
        "SELECT id, source, title FROM articles ORDER BY created_at DESC LIMIT %s", 
        (limit,)
    )

    for row in rows:
        original = row['title']
        print(f"\n[Original] {original}")
        
        # 1. Extract Entities
        ents = extract_entities(original)
        protected_text = original
        entity_map = {}
        
        for i, ent in enumerate(ents):
            name = ent['name']
            placeholder = f"[[E{i}]]"
            entity_map[placeholder] = name
            # Only replace if the name is reasonably unique to avoid partial matches
            if len(name) > 3:
                protected_text = protected_text.replace(name, placeholder)
        
        if entity_map:
            print(f"  🔒 Protected: {protected_text} ({entity_map})")
        else:
            print("  ⚪ No major entities found.")

        # 2. MK -> EN Bridge
        en_bridge = nllb_translate(protected_text, src_lang="mk", target_lang="en")
        if not en_bridge: continue
        
        # 3. EN -> MK Standard
        mk_standard = nllb_translate(en_bridge, src_lang="en", target_lang="mk")
        if not mk_standard: continue

        # 4. Restore Entities
        final_text = mk_standard
        for placeholder, original_name in entity_map.items():
            # Handle potential spaces/slight changes NLLB adds around brackets
            final_text = final_text.replace(placeholder, original_name)
            final_text = re.sub(r'\[\s*\[\s*E' + re.escape(placeholder[3:-2]) + r'\s*\]\s*\]', original_name, final_text)

        print(f"  ✨ Final Polished: {final_text}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(run_safe_polish_prototype())
