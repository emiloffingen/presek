import sys
import os
import logging
import datetime

# Ensure project root is in path
sys.path.append(os.getcwd())

import ai_engine
from tasks.delivery import (
    generate_daily_brief_task, 
    _load_daily_brief_clusters, 
    _build_daily_brief_context,
    _has_valid_daily_brief_structure,
    _is_grounded_daily_brief,
    _is_high_quality_briefing
)
from prompts import DAILY_BRIEF_SYSTEM_PROMPT
from database import db_manager as db
from utils import redis_client, delete_cache
from nlp import generate_daily_brief_fallback

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek")

def force_generate_with_mistral():
    print("🚀 Starting manual briefing generation with Mistral...")
    
    # 1. Force provider to Mistral in ai_engine
    class MistralOnlyProvider(ai_engine.MistralProvider):
        def call(self, prompt, system, max_tokens, json_mode, topic=None, task_type="default"):
            print(f"DEBUG: MistralOnlyProvider called for task: {task_type}")
            return super().call(prompt, system, max_tokens, json_mode, topic, task_type)

    ai_engine.PROVIDERS["mistral"] = MistralOnlyProvider()
    ai_engine.TASK_ROUTING["daily_brief"] = ["mistral"] # Disable fallback to local

    try:
        # 1. Gather Intelligence Stats
        total_24h = db.execute_one("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'")["count"] or 1
        intl_24h = db.execute_one("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND is_global = TRUE")["count"] or 0
        intl_pct = round((intl_24h / total_24h) * 100)
        
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
        diverse_pct = round((balance_stats["diverse"] / total_24h) * 100) if total_24h > 0 else 0

        # 2. Prep Dispatch Name
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12: dispatch_name = "Утрински Диспач"
        elif 12 <= hour < 18: dispatch_name = "Пладневен Преглед"
        else: dispatch_name = "Вечерен Преглед"

        # 3. Build AI Context
        clusters = _load_daily_brief_clusters(limit=6)
        content_context = _build_daily_brief_context(clusters)
        
        system_insight = (
            f"\n\n[СИСТЕМСКА АНАЛИЗА ЗА ПОСЛЕДНИТЕ 24Ч]\n"
            f"- Обработени статии: {total_24h}\n"
            f"- Удел на светски вести: {intl_pct}%\n"
            f"- Индекс на плурализам (разновидни извори): {diverse_pct}%\n"
            f"- Наслов на диспачот: {dispatch_name}"
        )
        
        full_context = content_context + system_insight

        print(f"📊 Stats: {total_24h} articles, {intl_pct}% global, {diverse_pct}% pluralism")
        print("🤖 Calling Mistral...")
        
        brief, provider = ai_engine._call_ai(full_context, DAILY_BRIEF_SYSTEM_PROMPT, task_type="daily_brief")
        
        if not brief:
            print("❌ Mistral returned nothing.")
            return

        print(f"✅ Mistral responded (via {provider}). Length: {len(brief)} chars.")

        if not _has_valid_daily_brief_structure(brief):
            print("⚠️ Invalid structure, but forcing save anyway for manual review if needed.")
        
        final_brief = brief
        if not final_brief.startswith("#"):
            final_brief = f"# {dispatch_name}\n\n" + final_brief
        
        db.execute("INSERT INTO daily_briefings (date, content) VALUES (CURRENT_DATE, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content", (final_brief,), fetch=False)
        
        # Clear locks and cache
        lock_key = f"lock:daily_brief:{datetime.date.today()}"
        redis_client.delete(lock_key)
        delete_cache("daily_brief:latest")
        
        print("✨ Success! New briefing generated and saved.")
        print("\n--- BRIEFING START ---\n")
        print(final_brief[:500] + "...")
        print("\n--- BRIEFING END ---")

    except Exception as e:
        print(f"💥 Error during manual generation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    force_generate_with_mistral()
