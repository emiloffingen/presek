
import database
import trending
import datetime

def check():
    conn = database.get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM articles")
    count = cur.fetchone()[0]
    print(f"Total articles: {count}")
    
    cur.execute("SELECT COUNT(*) FROM articles WHERE clicks > 0")
    clicks_count = cur.fetchone()[0]
    print(f"Articles with clicks > 0: {clicks_count}")
    
    cur.execute("SELECT MAX(created_at) FROM articles")
    latest = cur.fetchone()[0]
    print(f"Latest article: {latest}")
    
    cur.close()
    conn.close()
    
    print("\nTrending topics (get_trending):")
    results = trending.get_trending()
    print(results)

if __name__ == "__main__":
    check()
