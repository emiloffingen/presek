
from database import db_manager as db
import uuid

def fix_mixed_cluster(target_cluster_id):
    print(f"Investigating cluster {target_cluster_id}...")
    articles = db.execute("SELECT id, title, source, topic FROM articles WHERE cluster_id = %s", (target_cluster_id,))
    if not articles:
        print("No articles found.")
        return

    # Keywords for the main story (Gordana Duvnjak)
    main_keywords = ["Гордана", "Дувњак", "почина", "новинарка"]
    
    to_move = []
    for art in articles:
        title = art['title'].lower()
        is_main = any(k.lower() in title for k in main_keywords)
        if not is_main:
            to_move.append(art)
    
    print(f"Moving {len(to_move)} unrelated articles out of {target_cluster_id}...")
    
    # Simple strategy: give each unrelated article a new unique cluster ID
    # In a real scenario, we might want to re-cluster them properly, 
    # but for an emergency un-mix, isolation is safer.
    for art in to_move:
        new_cid = str(uuid.uuid4())[:8]
        db.execute("UPDATE articles SET cluster_id = %s WHERE id = %s", (new_cid, art['id']), fetch=False)
        # Also clean up metadata to force refresh
        db.execute("DELETE FROM cluster_metadata WHERE cluster_id = %s", (new_cid,), fetch=False)
        print(f"  - '{art['title'][:40]}...' -> {new_cid}")

    # Force metadata refresh for the original cluster
    db.execute("DELETE FROM cluster_metadata WHERE cluster_id = %s", (target_cluster_id,), fetch=False)
    print("Done.")

if __name__ == '__main__':
    fix_mixed_cluster('12603cd1')
