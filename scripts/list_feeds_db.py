from core.database import db_manager as db

def list_feeds():
    rows = db.execute("""
        SELECT s.name, s.url, s.country, fs.is_active as feed_active, s.is_active as source_active
        FROM sources s
        LEFT JOIN feed_sources fs ON s.name = fs.name
    """)
    
    mk_feeds = [r for r in rows if r['country'] == 'MK']
    rs_feeds = [r for r in rows if r['country'] == 'RS' or not r['country']]
    
    print(f"Macedonian Feeds ({len(mk_feeds)}):")
    for f in mk_feeds:
        print(f"  - {f['name']} ({f['url']}) [Source Active: {f['source_active']}, Feed Active: {f['feed_active']}]")
        
    print(f"\nSerbian Feeds ({len(rs_feeds)}):")
    for f in rs_feeds:
        print(f"  - {f['name']} ({f['url']}) [Source Active: {f['source_active']}, Feed Active: {f['feed_active']}]")

if __name__ == "__main__":
    list_feeds()
