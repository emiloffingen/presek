from core.database import db_manager as db

def check_sources_status():
    print("Checking RS sources status in DB:")
    rows = db.execute("""
        SELECT
            fs.name,
            fs.is_active as fs_active,
            s.is_active as s_active,
            s.pause_mode
        FROM feed_sources fs
        JOIN sources s ON fs.name = s.name
        WHERE s.country = 'RS'
    """)
    for r in rows:
        print(f"  - {r['name']}: feed_active={r['fs_active']}, source_active={r['s_active']}, pause_mode={r['pause_mode']}")

    print("\nChecking MK sources status in DB (sample 5):")
    rows = db.execute("""
        SELECT
            fs.name,
            fs.is_active as fs_active,
            s.is_active as s_active,
            s.pause_mode
        FROM feed_sources fs
        JOIN sources s ON fs.name = s.name
        WHERE s.country = 'MK'
        LIMIT 5
    """)
    for r in rows:
        print(f"  - {r['name']}: feed_active={r['fs_active']}, source_active={r['s_active']}, pause_mode={r['pause_mode']}")

if __name__ == "__main__":
    check_sources_status()
