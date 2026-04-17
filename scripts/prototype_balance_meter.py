
import asyncio
import logging
from database import db_manager as db
from config import SOURCE_CATEGORIES

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.balance_prototype")

# Define Pluralism Tiers
TIER_MAP = {
    "Агенциски": "Mainstream",
    "Јавен Сервис": "Mainstream",
    "Главни": "Mainstream",
    "Независни": "Independent",
    "Истражувачки": "Independent",
    "Регионални": "Regional/Alt",
    "Алтернативни": "Regional/Alt",
    "Локални": "Regional/Alt"
}

def get_cluster_diversity(articles):
    tiers_present = set()
    source_names = []
    
    for art in articles:
        source = art.get("source")
        cat = SOURCE_CATEGORIES.get(source, "Локални")
        tier = TIER_MAP.get(cat, "Regional/Alt")
        tiers_present.add(tier)
        source_names.append(f"{source} ({tier})")
        
    return tiers_present, source_names

async def run_balance_prototype(limit=5):
    print("\n--- Presek Media Pluralism & Balance Prototype ---")
    
    # Get top 5 clusters with at least 3 sources
    clusters = db.execute("""
        SELECT cluster_id, COUNT(*) as source_count 
        FROM articles 
        WHERE created_at >= NOW() - INTERVAL '48 hours'
        GROUP BY cluster_id 
        HAVING COUNT(*) >= 3
        ORDER BY source_count DESC 
        LIMIT %s
    """, (limit,))

    for c in clusters:
        cid = c['cluster_id']
        articles = db.execute("SELECT source, title FROM articles WHERE cluster_id = %s", (cid,))
        
        title = articles[0]['title'][:70] + "..."
        tiers, sources = get_cluster_diversity(articles)
        
        print(f"\n[Story] {title}")
        print(f"  📊 Sources: {', '.join(sources)}")
        
        if len(tiers) >= 3:
            verdict = "💎 HIGH PLURALISM (Agency + Independent + Regional)"
            badge = "Широк Консензус"
        elif len(tiers) == 2:
            verdict = "✅ BALANCED COVERAGE (Mixed Media Groups)"
            badge = "Разновидни Извори"
        else:
            verdict = "⚠️ ECHO CHAMBER (Reported only by one media group)"
            badge = "Еднострано"
            
        print(f"  ⚖️ Verdict: {verdict}")
        print(f"  🏷️ UI Badge: [{badge}]")
        print("-" * 60)

if __name__ == "__main__":
    asyncio.run(run_balance_prototype())
