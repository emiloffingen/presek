import sys
import os
import logging
import datetime

# Ensure project root is in path
sys.path.append(os.getcwd())

import ai_engine
from tasks.delivery import (
    _load_daily_brief_clusters, 
    _build_daily_brief_context
)
from prompts import DAILY_BRIEF_SYSTEM_PROMPT
from database import db_manager as db
from utils import delete_cache

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek")

def force_generate_with_local():
    log.info("Starting manual briefing generation with MISTRAL...")

    # Force provider to MISTRAL in ai_engine
    ai_engine.PROVIDER_FALLBACK_ORDER = ["mistral"]
    ai_engine.PROVIDER_FALLBACK_ORDER_SUMMARY = ["mistral"]
    ai_engine.PROVIDER_FALLBACK_ORDER_RESEARCH = ["mistral"]


    try:
        # 1. Gather Intelligence Stats
        total_24h = db.execute_one("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'")["count"] or 1
        intl_24h = db.execute_one("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND category IN ('Свет', 'Европа', 'Балкан')")["count"] or 0
        intl_pct = round((intl_24h / total_24h) * 100)
        
        # 2. Prep Dispatch Name
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12: dispatch_name = "Утрински Диспач (Mistral)"
        elif 12 <= hour < 18: dispatch_name = "Пладневен Преглед (Mistral)"
        else: dispatch_name = "Вечерен Преглед (Mistral)"

        # 3. Build AI Context (Limiting to 4 clusters to fit in Gemma context)
        clusters = _load_daily_brief_clusters(limit=4)
        content_context = _build_daily_brief_context(clusters)
        
        system_insight = (
            f"\n\n[СИСТЕМСКА АНАЛИЗА ЗА ПОСЛЕДНИТЕ 24Ч]\n"
            f"- Обработени статии: {total_24h}\n"
            f"- Удел на меѓународни вести: {intl_pct}%\n"
            f"- Наслов на диспачот: {dispatch_name}"
        )
        
        full_context = content_context + system_insight

        log.info(f"Stats: {total_24h} articles, {intl_pct}% intl")
        log.info("Calling Local Analyst...")
        
        # We increase max_tokens slightly for the long brief
        brief, provider = ai_engine._call_ai(full_context, DAILY_BRIEF_SYSTEM_PROMPT, task_type="daily_brief", max_tokens=1500)
        
        if not brief:
            log.error("Local Analyst returned nothing.")
            return

        log.info(f"Local Analyst responded (via {provider}). Length: {len(brief)} chars.")
        
        final_brief = brief
        if not final_brief.startswith("#"):
            final_brief = f"# {dispatch_name}\n\n" + final_brief
        
        db.execute("INSERT INTO daily_briefings (date, content) VALUES (CURRENT_DATE, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content", (final_brief,), fetch=False)
        
        # Clear cache
        delete_cache("daily_brief:latest")
        
        log.info("Success! New LOCAL briefing generated and saved.")
        print("-" * 30)
        print(final_brief[:1000] + "...")
        print("-" * 30)

    except Exception as e:
        log.error(f"Error during local manual generation: {e}")
        log.exception("Full traceback")

if __name__ == "__main__":
    force_generate_with_local()
