import os
import sys
import json
import re

# Ensure project root is in path
_ROOT = os.path.abspath(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from database import db_manager as db

def clean_summary(text):
    if not text:
        return text
    
    text = text.strip()
    
    # Remove markdown code fences
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    if text.startswith('{') and text.endswith('}'):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'summary' in data:
                return data['summary']
        except (json.JSONDecodeError, TypeError):
            # Manual fallback for broken JSON
            m = re.search(r'"summary":\s*"(.*)"', text, re.DOTALL)
            if m:
                return m.group(1).replace('\\"', '"')
    
    return text

def run_cleanup():
    rows = db.execute("SELECT id, summary FROM articles WHERE summary LIKE '{%' OR summary LIKE '```%'")
    if not rows:
        print("No malformed summaries found.")
        return

    print(f"Found {len(rows)} potentially malformed summaries. Cleaning...")
    
    count = 0
    for row in rows:
        cleaned = clean_summary(row['summary'])
        if cleaned != row['summary']:
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (cleaned, row['id']), fetch=False)
            count += 1
            if count % 100 == 0:
                print(f"Cleaned {count} summaries...")

    print(f"Done. Successfully cleaned {count} summaries.")

if __name__ == "__main__":
    run_cleanup()
