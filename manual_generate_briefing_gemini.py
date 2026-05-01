import sys
import os
import logging
import datetime
from dotenv import load_dotenv

# Ensure project root is in path
sys.path.append(os.getcwd())

# Load environment variables from .env
load_dotenv()

import ai_engine
from tasks.delivery import (
    _load_daily_brief_clusters, 
    _build_daily_brief_context,
    _has_valid_daily_brief_structure
)
from prompts import DAILY_BRIEF_SYSTEM_PROMPT
from database import db_manager as db
from utils import redis_client, delete_cache

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek")

def generate_with_gemini():
    log.info("Starting manual briefing generation with Gemini...")
    
    try:
        # 1. Gather Intelligence Stats
        total_24h_res = db.execute_one("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'")
        total_24h = total_24h_res["count"] if total_24h_res else 1
        
        intl_24h_res = db.execute_one("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND is_global = TRUE")
        intl_24h = intl_24h_res["count"] if intl_24h_res else 0
        
        intl_pct = round((intl_24h / max(1, total_24h)) * 100)
        
        balance_stats = db.execute_one("""
            WITH cluster_tiers AS (
                SELECT cluster_id, COUNT(DISTINCT 
                    CASE 
                        WHEN s.category IN ('Агенциски', 'Јавен Сервис', 'Главни') THEN 'M'
                        WHEN s.category IN ('Независни', 'Истражувачки') THEN 'I'
                        ELSE 'R'
                    END) as group_count
                FROM articles a
                JOIN sources s ON a.source = s.name
                WHERE a.created_at >= NOW() - INTERVAL '24 hours'
                GROUP BY cluster_id
            )
            SELECT COUNT(*) FILTER (WHERE group_count >= 2) as diverse
            FROM cluster_tiers
        """)
        diverse_count = balance_stats["diverse"] if balance_stats else 0
        diverse_pct = round((diverse_count / max(1, total_24h)) * 100)

        # 2. Prep Dispatch Name
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12: 
            dispatch_name = "Утрински Диспач"
            time_label = "утрински"
        elif 12 <= hour < 18: 
            dispatch_name = "Пладневен Преглед"
            time_label = "пладневен"
        else: 
            dispatch_name = "Вечерен Преглед"
            time_label = "вечерен"
        
        date_str = datetime.datetime.now().strftime("%A, %d %B %Y")

        # 3. Build AI Context
        clusters = _load_daily_brief_clusters(limit=6)
        content_context = _build_daily_brief_context(clusters)
        
        # Calculate distinct actors
        all_actors = set()
        for c in clusters:
            all_actors.update(c.get("entities", []))
            
        system_insight = (
            f"\n\n[СИСТЕМСКА АНАЛИЗА]\n"
            f"- Датум: {date_str}\n"
            f"- Тип на преглед: {time_label}\n"
            f"- Вкупно следени објави (24ч): {total_24h}\n"
            f"- Издвоени актери: {len(all_actors)}\n"
        )
        
        full_context = content_context + system_insight

        log.info(f"Stats: {total_24h} articles, {intl_pct}% global, {diverse_pct}% pluralism")
        log.info("Calling Gemini...")
        
        # Explicitly use gemini provider if available
        brief, provider = ai_engine._call_ai(full_context, DAILY_BRIEF_SYSTEM_PROMPT, task_type="daily_brief")
        
        if not brief:
            log.error("Gemini returned nothing.")
            return

        log.info(f"Gemini responded (via {provider}). Length: {len(brief)} chars.")
        
        if not _has_valid_daily_brief_structure(brief):
            log.warning("Invalid structure detected in Gemini response.")
        
        final_brief = brief
        if not final_brief.strip().startswith("#"):
            final_brief = f"# {dispatch_name}\n\n" + final_brief
        
        db.execute("INSERT INTO daily_briefings (date, content) VALUES (CURRENT_DATE, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content", (final_brief,), fetch=False)
        
        # Clear locks and cache
        lock_key = f"lock:daily_brief:{datetime.date.today()}"
        redis_client.delete(lock_key)
        delete_cache("daily_brief:latest")
        
        log.info("Success! New briefing generated and saved.")
        print("--- BRIEFING PREVIEW ---")
        print(final_brief[:1000] + "...")
        print("--- END PREVIEW ---")

    except Exception as e:
        log.error(f"Error during manual generation: {e}")
        log.exception("Full traceback")

if __name__ == "__main__":
    generate_with_gemini()
