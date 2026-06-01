import asyncio
import sys

sys.path.append("/home/emiloffingen/presek")

from core.database import db_manager as db
from core.ai_engine import sync_call_ai as _call_ai
from core.prompts import SYNTHESIS_SYSTEM_PROMPT_SR
from tasks.intelligence import synthesize_cluster_task

async def main():
    cluster_id = "1e54ebcce23a"
    lang = "sr"
    
    # Get articles
    articles = await db.async_execute(
        "SELECT id, title, description, full_content, source, created_at FROM articles WHERE cluster_id = %s",
        (cluster_id,)
    )
    
    if not articles:
        print("No articles found for cluster!")
        return
        
    print(f"Found {len(articles)} articles.")
    
    # Build prompt
    prompt_parts = []
    prompt_parts.append(
        "Zadatak: Kreiraj urednički izveštaj o sledećim novim člancima. Vrati isključivo validan JSON."
    )
    prompt_parts.append("novi clanci OD danas:\n<articles_context>")
    
    context_lines = []
    for a in articles:
        context_lines.append(f"Source: {a['source']}\nTitle: {a['title']}\nDescription: {a.get('description') or ''}\nContent: {a.get('full_content') or ''}\n---")
    
    prompt_parts.append("\n".join(context_lines))
    prompt_parts.append("</articles_context>")
    
    full_prompt = "\n\n".join(part for part in prompt_parts if part)
    
    print("Calling Mistral Large...")
    raw, provider = _call_ai(
        full_prompt,
        SYNTHESIS_SYSTEM_PROMPT_SR,
        json_mode=True,
        task_type="synthesis",
        max_tokens=3000,
        lang=lang,
        provider_override="mistral_large"
    )
    
    print("\n--- RAW RESPONSE ---")
    print(raw)
    print("--------------------\n")
    
    if raw:
        # Let's inspect control characters
        for idx, char in enumerate(raw):
            if ord(char) < 0x20 and char not in ('\n', '\r', '\t', ' '):
                print(f"Control char found: ord={ord(char)} at index {idx}")

if __name__ == "__main__":
    asyncio.run(main())
