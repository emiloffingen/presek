import os
import sys
import logging
from dotenv import load_dotenv

# Ensure we can import from the root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import db_manager as db
from ai_engine import PROVIDERS
from prompts import SUMMARY_SYSTEM_PROMPT

def compare_summaries():
    load_dotenv()
    logging.basicConfig(level=logging.WARNING) # Shhh

    # Fetch 3 diverse articles: one likely with long content, two standard
    articles = db.execute(
        "SELECT id, title, description, full_content, source, category "
        "FROM articles "
        "WHERE description IS NOT NULL AND length(description) > 300 "
        "ORDER BY created_at DESC LIMIT 3"
    )

    if not articles:
        print("No suitable articles found for comparison.")
        return

    print("="*80)
    print(f"{'AI SUMMARY COMPARISON':^80}")
    print("="*80)

    for i, art in enumerate(articles, 1):
        title = art['title']
        # Prioritize full_content if the new crawler got it, otherwise description
        content = art['full_content'] if art.get('full_content') and len(art['full_content']) > 200 else art['description']
        source = art['source']
        category = art['category']

        prompt = f"Наслов: {title}\nТекст: {content[:2000]}" # Limit for test

        print(f"\n[{i}] ИЗВОР: {source} | КАТЕГОРИЈА: {category}")
        print(f"НАСЛОВ: {title}")
        print("-" * 40)

        # 1. Local Summary
        try:
            local_res = PROVIDERS["local"].call(prompt, SUMMARY_SYSTEM_PROMPT, 500, False)
            print(f"\n>>> LOCAL NLP (Free & Deterministic):")
            print(f"{local_res}")
        except Exception as e:
            print(f"Local failed: {e}")

        # 2. Mistral Summary
        try:
            mistral_res = PROVIDERS["mistral"].call(prompt, SUMMARY_SYSTEM_PROMPT, 500, True)
            # Mistral returns JSON, let's try to extract it cleanly
            import json
            try:
                data = json.loads(mistral_res)
                mistral_text = data.get('summary', mistral_res)
            except:
                mistral_text = mistral_res
            
            print(f"\n>>> MISTRAL AI (High Reasoning & Paid):")
            print(f"{mistral_text}")
        except Exception as e:
            print(f"Mistral failed: {e}")

        print("\n" + "="*80)

if __name__ == "__main__":
    compare_summaries()
