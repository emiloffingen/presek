import json
import re

from core.database import db_manager as db
from core.language import transliterate_lat_to_cyr


def has_latin(text):
    if not text:
        return False
    return bool(re.search(r'[A-Za-z]', text))

def fix():
    rows = db.execute("SELECT cluster_id, lang, summary, generated_article, synthetic_headline, synthetic_standfirst, key_facts, perspectives, verification_report FROM cluster_summaries WHERE lang = 'mk' AND created_at >= NOW() - INTERVAL '48 hours'")
    print(f"Checking {len(rows)} Macedonian summaries for Latin script mixing...")
    
    fixed_count = 0
    for r in rows:
        needs_fix = False
        cid = r['cluster_id']
        
        # Fields to check and fix
        summary = r['summary']
        article = r['generated_article']
        headline = r['synthetic_headline']
        standfirst = r['synthetic_standfirst']
        
        if has_latin(summary) or has_latin(article) or has_latin(headline) or has_latin(standfirst):
            needs_fix = True
            summary = transliterate_lat_to_cyr(summary)
            article = transliterate_lat_to_cyr(article)
            headline = transliterate_lat_to_cyr(headline)
            standfirst = transliterate_lat_to_cyr(standfirst)
            
        # JSON fields
        key_facts = r['key_facts']
        if has_latin(str(key_facts)):
            needs_fix = True
            if isinstance(key_facts, list):
                key_facts = [transliterate_lat_to_cyr(f) for f in key_facts]
            elif isinstance(key_facts, str):
                key_facts = transliterate_lat_to_cyr(key_facts)

        perspectives = r['perspectives']
        if has_latin(str(perspectives)):
            needs_fix = True
            if isinstance(perspectives, list):
                for p in perspectives:
                    p['angle'] = transliterate_lat_to_cyr(p.get('angle', ''))
                    p['content'] = transliterate_lat_to_cyr(p.get('content', ''))
            elif isinstance(perspectives, str):
                 perspectives = transliterate_lat_to_cyr(perspectives)

        verification = r['verification_report']
        if has_latin(str(verification)):
            needs_fix = True
            if isinstance(verification, dict):
                for k in ['agreements', 'conflicts', 'missing_info']:
                    if k in verification and isinstance(verification[k], list):
                        verification[k] = [transliterate_lat_to_cyr(item) for item in verification[k]]
            elif isinstance(verification, str):
                verification = transliterate_lat_to_cyr(verification)

        if needs_fix:
            db.execute(
                """UPDATE cluster_summaries 
                   SET summary = %s, generated_article = %s, synthetic_headline = %s, 
                       synthetic_standfirst = %s, key_facts = %s, perspectives = %s, 
                       verification_report = %s 
                   WHERE cluster_id = %s AND lang = 'mk'""",
                (summary, article, headline, standfirst, 
                 json.dumps(key_facts) if not isinstance(key_facts, str) else key_facts, 
                 json.dumps(perspectives) if not isinstance(perspectives, str) else perspectives, 
                 json.dumps(verification) if not isinstance(verification, str) else verification, 
                 cid),
                fetch=False
            )
            fixed_count += 1

    print(f"Successfully fixed {fixed_count} mixed (Latin) summaries on Macedonian site.")

if __name__ == '__main__':
    fix()
