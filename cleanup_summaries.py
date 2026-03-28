
import database
import json
import os
import re

def clean_json_response(text: str) -> str:
    if not text:
        return ""
    # Strip markdown code blocks
    text = re.sub(r'```(?:json)?\n?', '', text)
    text = text.replace('```', '').strip()
    
    # Try to find JSON
    start_brace = text.find('{')
    end_brace = text.rfind('}')
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        json_part = text[start_brace:end_brace+1]
        try:
            data = json.loads(json_part)
            if isinstance(data, dict) and 'summary' in data:
                return data['summary'].strip()
        except:
            pass
    return text.strip()

def cleanup():
    # 1. Clean cluster_summaries.json
    cache_path = "cluster_summaries.json"
    if os.path.exists(cache_path):
        print(f"Cleaning {cache_path}...")
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        
        cleaned_cache = {k: clean_json_response(v) for k, v in cache.items()}
        
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cleaned_cache, f, ensure_ascii=False, indent=2)
        print(f"Cleaned {len(cleaned_cache)} items in {cache_path}.")

    # 2. Clean database tables
    if os.path.exists("presek.db"):
        print("Cleaning presek.db...")
        conn = database.get_db()
        conn.row_factory = sqlite3.Row
        
        # Clean articles table (lead summaries)
        articles = conn.execute("SELECT id, summary FROM articles WHERE summary IS NOT NULL AND summary != ''").fetchall()
        for art in articles:
            cleaned = clean_json_response(art['summary'])
            if cleaned != art['summary']:
                conn.execute("UPDATE articles SET summary = %s WHERE id = %s", (cleaned, art['id']))
        print(f"Cleaned {len(articles)} summaries in articles table.")

        # Clean cluster_summaries table
        try:
            summaries = conn.execute("SELECT cluster_id, summary FROM cluster_summaries").fetchall()
            for s in summaries:
                cleaned = clean_json_response(s['summary'])
                if cleaned != s['summary']:
                    conn.execute("UPDATE cluster_summaries SET summary = %s WHERE cluster_id = %s", (cleaned, s['cluster_id']))
            print(f"Cleaned {len(summaries)} summaries in cluster_summaries table.")
        except:
            print("cluster_summaries table not found or empty.")

        conn.commit()
        conn.close()
        print("Database cleanup complete.")

if __name__ == "__main__":
    cleanup()
