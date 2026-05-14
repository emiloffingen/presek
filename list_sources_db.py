from database import db_manager as db

def list_sources():
    print("All time sources for RS:")
    rows = db.execute("SELECT DISTINCT source FROM articles WHERE country = 'RS'")
    for r in rows:
        print(f"  - {r['source']}")
    
    print("\nAll time sources for MK:")
    rows = db.execute("SELECT DISTINCT source FROM articles WHERE country = 'MK'")
    for r in rows:
        print(f"  - {r['source']}")

if __name__ == "__main__":
    list_sources()
