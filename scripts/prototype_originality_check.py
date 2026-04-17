
import asyncio
import logging
import feedparser
import httpx
from database import db_manager as db
from nllb_translate import translate as nllb_translate
from embeddings import generate_query_embedding
import numpy as np

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.originality")

GLOBAL_FEED = "https://www.reutersagency.com/feed/?best-topics=world-news&post_type=best"

def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

async def run_originality_prototype(limit=5):
    print("\n--- Presek Source Originality Prototype (NLLB + MiniLM) ---")
    
    # 1. Fetch Global Headlines (English)
    print("📡 Fetching Global 'Gold Standard' (Reuters)...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(GLOBAL_FEED)
        global_feed = feedparser.parse(resp.text)
        global_titles = [e.title for e in global_feed.entries[:30]]
    
    if not global_titles:
        print("Failed to fetch global reference. Using hardcoded fallback.")
        global_titles = ["Iran", "Trump", "Gaza", "Ukraine", "Oil prices", "Tesla", "AI news"]

    # 2. Get Macedonian Articles
    rows = db.execute(
        "SELECT id, source, title FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' LIMIT %s",
        (limit,)
    )

    # 3. Analyze
    for row in rows:
        mk_title = row['title']
        print(f"\n[MK Source: {row['source']}] {mk_title}")
        
        # A. Translate MK -> EN
        en_version = nllb_translate(mk_title, src_lang="mk", target_lang="en")
        print(f"  ✨ English Bridge: {en_version}")
        
        if not en_version: continue

        # B. Generate embedding for our bridge
        mk_vec = generate_query_embedding(en_version)
        
        # C. Compare against global list
        best_score = 0
        best_match = ""
        
        for g_title in global_titles:
            g_vec = generate_query_embedding(g_title)
            score = cosine_similarity(mk_vec, g_vec)
            if score > best_score:
                best_score = score
                best_match = g_title
        
        # D. Verdict
        if best_score > 0.80:
            verdict = "🌍 GLOBAL NEWS (Likely Translated)"
        elif best_score > 0.65:
            verdict = "🔗 REGIONAL/SHARED INTEREST"
        else:
            verdict = "🇲🇰 LOCAL ORIGINAL REPORTING"
            
        print(f"  🔍 Closest Global Match: \"{best_match}\" (Score: {best_score:.4f})")
        print(f"  ⚖️ Verdict: {verdict}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(run_originality_prototype())
