from core.database import db_manager as db

def check_recent_ingestion():
    rows = db.execute("""
        SELECT country, source, COUNT(*) as count
        FROM articles
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        GROUP BY country, source
        ORDER BY country, count DESC
    """)
    
    print("Recent Ingestion (last 24h):")
    current_country = None
    for r in rows:
        if r['country'] != current_country:
            current_country = r['country']
            print(f"\nCountry: {current_country or 'Unknown'}")
        print(f"  - {r['source']}: {r['count']} articles")

if __name__ == "__main__":
    check_recent_ingestion()
