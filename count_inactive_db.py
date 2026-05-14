from database import db_manager as db

def count_inactive_sources():
    rows = db.execute("SELECT country, COUNT(*) as count FROM sources WHERE is_active = FALSE GROUP BY country")
    print("Inactive sources in DB:")
    for r in rows:
        print(f"  - {r['country']}: {r['count']}")
    
    total = sum(r['count'] for r in rows)
    print(f"Total inactive: {total}")

if __name__ == "__main__":
    count_inactive_sources()
