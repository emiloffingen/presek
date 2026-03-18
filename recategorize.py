"""
recategorize.py — Re-run category detection on all articles.
Usage: python3 recategorize.py          (dry run — shows changes)
       python3 recategorize.py --apply  (applies changes to DB)
"""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from categories import detect_category, detect_subcategory

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presek.db")
apply = "--apply" in sys.argv

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, title, description, source, category, subcategory FROM articles").fetchall()

changed_cat = 0
changed_sub = 0
total = len(rows)

for r in rows:
    new_cat = detect_category(r["title"], r["description"] or "", r["source"] or "")
    new_sub = detect_subcategory(r["title"], r["description"] or "")
    
    cat_changed = new_cat != r["category"]
    sub_changed = (new_sub or "") != (r["subcategory"] or "")
    
    if cat_changed:
        changed_cat += 1
        if not apply and changed_cat <= 20:
            print(f"  CAT: {r['category']:15s} → {new_cat:15s} | {r['title'][:70]}")
    
    if cat_changed or sub_changed:
        if apply:
            conn.execute(
                "UPDATE articles SET category=?, subcategory=? WHERE id=?",
                (new_cat, new_sub or "", r["id"])
            )
        if sub_changed:
            changed_sub += 1

if apply:
    conn.commit()
    print(f"Applied: {changed_cat} category changes, {changed_sub} subcategory changes out of {total} articles")
else:
    print(f"\nDry run: {changed_cat} category changes, {changed_sub} subcategory changes out of {total} articles")
    print("Run with --apply to save changes")

conn.close()
