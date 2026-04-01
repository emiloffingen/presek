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
        except json.JSONDecodeError:
            pass
    return text.strip()

def cleanup():
    # 1. Database tables
    print("Cleaning database tables (PostgreSQL)...")
    try:
        conn = database.get_db()
        
        # Clean articles table (lead summaries)
        articles = conn.execute("SELECT id, summary FROM articles WHERE summary IS NOT NULL AND summary != ''").fetchall()
        count_art = 0
        for art in articles:
            cleaned = clean_json_response(art['summary'])
            if cleaned != art['summary']:
                conn.execute("UPDATE articles SET summary = %s WHERE id = %s", (cleaned, art['id']))
                count_art += 1
        print(f"Cleaned {count_art}/{len(articles)} summaries in articles table.")

        # Clean cluster_summaries table
        summaries = conn.execute("SELECT cluster_id, summary FROM cluster_summaries").fetchall()
        count_cls = 0
        for s in summaries:
            cleaned = clean_json_response(s['summary'])
            if cleaned != s['summary']:
                conn.execute("UPDATE cluster_summaries SET summary = %s WHERE cluster_id = %s", (cleaned, s['cluster_id']))
                count_cls += 1
        print(f"Cleaned {count_cls}/{len(summaries)} summaries in cluster_summaries table.")

        conn.commit()
        conn.close()
        print("Database cleanup complete.")
    except Exception as e:
        print(f"Database cleanup failed: {e}")

if __name__ == "__main__":
    cleanup()
