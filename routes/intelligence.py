import datetime
import json
import asyncio
import logging
import re
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException

from database import db_manager as db
from embeddings import generate_query_embedding
from utils import cached_response, set_cache, score_cluster
from nlp import normalize_tag_name
from entities import normalize_entity_name
from .common import cleanAndDecode, _is_valid_focus_entity
from .security import validate_cluster_id, validate_list_param, validate_string_param

log = logging.getLogger("presek")
router = APIRouter()

_FOCUS_ENTITY_GENERIC_SINGLE_WORDS = {
    "договор",
    "теснец",
    "реакции",
    "одлука",
    "мерки",
    "избори",
}

def _compact_focus_entities(items: list[dict], limit: int) -> list[dict]:
    by_key = {str(item.get("name") or "").casefold(): dict(item) for item in items if str(item.get("name") or "").strip()}

    # Merge common fragmented geopolitics phrase into one canonical entity.
    if "ормуз" in by_key and "теснец" in by_key:
        merged_mentions = max(
            int(by_key.get("ормуз", {}).get("total_mentions") or 0),
            int(by_key.get("теснец", {}).get("total_mentions") or 0),
            int(by_key.get("ормуски теснец", {}).get("total_mentions") or 0),
        )
        by_key["ормуски теснец"] = {
            "name": "Ормуски Теснец",
            "type": by_key.get("ормуски теснец", {}).get("type") or "LOC",
            "total_mentions": merged_mentions,
        }
        by_key.pop("ормуз", None)
        by_key.pop("теснец", None)

    compact = []
    for item in sorted(by_key.values(), key=lambda entry: int(entry.get("total_mentions") or 0), reverse=True):
        name = str(item.get("name") or "").strip()
        key = name.casefold()
        words = [word for word in re.split(r"\s+", key) if word]
        if len(words) == 1 and key in _FOCUS_ENTITY_GENERIC_SINGLE_WORDS:
            continue
        compact.append(item)
        if len(compact) >= limit:
            break
    return compact

@router.get("/intelligence/pulse-overview")
async def get_pulse_overview():
    """Provides a high-level summary of the media landscape (free, token-less)."""
    cache_key = "api:intelligence:pulse-overview"
    cached = cached_response(cache_key)
    if cached: return cached

    # 1. Trending Entities (Last 48h)
    trending = await db.async_execute("""
        SELECT name, total_mentions, sentiment_score, type
        FROM knowledge_entities
        WHERE last_seen >= NOW() - INTERVAL '48 hours'
        ORDER BY total_mentions DESC
        LIMIT 10
    """)

    # 2. Sentiment Extremes
    positives = await db.async_execute("""
        SELECT name, sentiment_score
        FROM knowledge_entities
        WHERE total_mentions >= 5 AND last_seen >= NOW() - INTERVAL '7 days'
        ORDER BY sentiment_score DESC
        LIMIT 5
    """)
    
    negatives = await db.async_execute("""
        SELECT name, sentiment_score
        FROM knowledge_entities
        WHERE total_mentions >= 5 AND last_seen >= NOW() - INTERVAL '7 days'
        ORDER BY sentiment_score ASC
        LIMIT 5
    """)

    # 3. Hot Relationships (Duos)
    relationships = await db.async_execute("""
        SELECT entity_a, entity_b, weight
        FROM knowledge_relationships
        WHERE last_seen >= NOW() - INTERVAL '48 hours'
        ORDER BY weight DESC
        LIMIT 6
    """)

    result = {
        "trending": trending,
        "sentiment": {
            "positives": positives,
            "negatives": negatives
        },
        "relationships": relationships,
        "updated_at": (await db.async_execute_one("SELECT MAX(last_seen) as last FROM knowledge_entities"))["last"]
    }
    
    set_cache(cache_key, result, ttl=600)
    return result

@router.get("/intelligence/cluster/{cluster_id}/history")
async def get_cluster_storyline_history(cluster_id: str):
    """Finds related clusters from the past weeks to build a storyline (free, token-less)."""
    validate_cluster_id(cluster_id)
    
    # Get current cluster's embedding (avg of its articles)
    rows = await db.async_execute("SELECT embedding FROM articles WHERE cluster_id = %s AND embedding IS NOT NULL", (cluster_id,))
    if not rows:
        return {"history": []}
    
    import numpy as np
    import json
    
    vecs = []
    for r in rows:
        vecs.append(json.loads(r['embedding']) if isinstance(r['embedding'], str) else list(r['embedding']))
    
    if not vecs:
        return {"history": []}
    
    avg_vec = np.mean(vecs, axis=0).tolist()
    vec_str = "[" + ",".join(map(str, avg_vec)) + "]"
    
    # Search for similar clusters from the past 30 days
    # We group by cluster_id and join with metadata for images
    related_clusters = await db.async_execute("""
        SELECT a.cluster_id,
               MAX(a.title) as title,
               MIN(a.created_at) as first_seen,
               (1 - (MIN(a.embedding <=> %s::vector))) as similarity,
               MAX(cm.representative_image) as image_url
        FROM articles a
        LEFT JOIN cluster_metadata cm ON a.cluster_id = cm.cluster_id
        WHERE a.embedding IS NOT NULL
          AND a.cluster_id != %s
          AND a.created_at >= NOW() - INTERVAL '30 days'
        GROUP BY a.cluster_id
        HAVING (1 - (MIN(a.embedding <=> %s::vector))) > 0.60
        ORDER BY first_seen DESC
        LIMIT 10
    """, (vec_str, cluster_id, vec_str))

    return {"history": related_clusters}
@router.get("/intelligence/cluster/{cluster_id}/research")
async def get_deep_research(cluster_id: str):
    """
    Performs a structured deep-dive analysis using the configured paid AI provider.
    """
    validate_cluster_id(cluster_id)
    cache_key = f"api:intelligence:research:{cluster_id}:v1"
    cached = cached_response(cache_key)
    if cached: return cached

    # 1. Get cluster context
    row = await db.async_execute_one("""
        SELECT a.title, s.summary 
        FROM articles a 
        LEFT JOIN cluster_summaries s ON a.cluster_id = s.cluster_id 
        WHERE a.cluster_id = %s 
        ORDER BY a.created_at DESC LIMIT 1
    """, (cluster_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Cluster not found")

    title = row["title"]
    summary = row["summary"] or ""
    
    # 2. Build the 'Researcher' Prompt
    system_prompt = (
        "Ти си врвен Аналитичар за новинската агенција 'Пресек'. "
        "Твоја задача е да направиш ДЛАБОКА АНАЛИЗА на дадена вест користејќи го дадениот контекст и твоето општо знаење за дополнителна рамка. "
        "Дај структуриран одговор на македонски јазик во неколку секции:\n"
        "1. 🔑 Клучни факти и бројки\n"
        "2. ⚖️ Ставови и реакции на засегнатите страни\n"
        "3. ✅ Што е потврдено, а што останува нејасно\n"
        "4. 💡 Широк контекст и минати настани поврзани со ова\n"
        "Биди објективен, професионален и детален."
    )
    
    user_prompt = f"Тема: {title}\n\nПостоечко резиме: {summary}\n\nДај длабок контекст, релевантни детали и јасно оддели што е потврдено од дадениот материјал од пошироката аналитичка рамка."

    try:
        from ai_engine import sync_call_ai
        response, provider = await asyncio.to_thread(
            sync_call_ai,
            prompt=user_prompt,
            system=system_prompt,
            task_type="research",
            max_tokens=1500,
        )
        
        if not response:
            return {"status": "error", "message": "Системот моментално не е достапен."}

        result = {
            "status": "success",
            "research": response,
            "provider": provider,
            "timestamp": datetime.datetime.now()
        }
        
        set_cache(cache_key, result, ttl=3600) # Cache for 1 hour
        return result
        
    except Exception as e:
        log.error(f"Deep Research Error: {e}", exc_info=True)
        return {"status": "error", "message": "Грешка при пребарувањето."}

@router.get("/intelligence/cluster/{cluster_id}/analyst")
async def get_cluster_analyst_report(cluster_id: str, mode: str = "facts"):
    """
    Internal 'Deep Intel' Analyst.
    Uses full content and a hybrid Local+Mistral approach.
    Modes: 'facts', 'perspectives', 'context'
    """
    validate_cluster_id(cluster_id)
    cache_key = f"api:intelligence:analyst:{cluster_id}:{mode}:v2"
    cached = cached_response(cache_key)
    if cached: return cached

    # 1. Fetch all full content
    arts = await db.async_execute("SELECT title, full_content, source, category, embedding FROM articles WHERE cluster_id = %s", (cluster_id,))
    if not arts:
        raise HTTPException(status_code=404, detail="Cluster not found")

    combined_text = "\n\n".join([f"--- ИЗВОР: {a['source']} ---\n{a['full_content'] or a['title']}" for a in arts[:5]])
    
    # 1.5 Fetch Data-Driven Context for 'context' mode
    history_context = ""
    if mode == "context":
        try:
            import numpy as np
            import json
            vecs = [json.loads(a['embedding']) if isinstance(a['embedding'], str) else list(a['embedding']) for a in arts if a.get('embedding')]
            if vecs:
                avg_vec = np.mean(vecs, axis=0).tolist()
                vec_str = "[" + ",".join(map(str, avg_vec)) + "]"
                # Find historically similar clusters (excluding today)
                past_events = await db.async_execute("""
                    SELECT title, created_at, category
                    FROM articles
                    WHERE embedding IS NOT NULL AND cluster_id != %s
                      AND created_at < NOW() - INTERVAL '24 hours'
                    ORDER BY (embedding <=> %s::vector) ASC
                    LIMIT 5
                """, (cluster_id, vec_str))
                if past_events:
                    history_list = "\n".join([f"- {p['title']} ({p['created_at'].strftime('%d.%m.%Y')})" for p in past_events])
                    history_context = f"\n\nРЕАЛНА ИСТОРИСКА ПОЗАДИНА ОД БАЗАТА (Користи го ова за контекст):\n{history_list}"
        except Exception as e:
            log.warning(f"Failed to fetch analyst history context: {e}")

    # 2. Select Prompt based on Mode
    prompts = {
        "facts": (
            "Ти си Економски Аналитичар за 'Пресек'. Твоја задача е да извлечеш клучни бројки, датуми и статистика.\n\n"
            "СТРУКТУРА НА ОДГОВОРОТ:\n"
            "1. # Сумарен преглед: Еден концизен воведен пасус (Lead).\n"
            "2. # Клучни показатели: Јасни булети со најважните податоци. Користи БОЛД за сите бројки (пр. **15%**, **200 милиони**).\n"
            "3. # Хронологија: Ако веста има временска рамка, претстави ја во булети.\n\n"
            "ПРАВИЛА: Не измислувај бројки. Не користи емоџи. Биди професионален."
        ),
        "perspectives": (
            "Ти си Политички Аналитичар за 'Пресек'. Анализирај ги ставовите на клучните актери.\n\n"
            "СТРУКТУРА НА ОДГОВОРОТ:\n"
            "1. # Главниот спор: Опиши го јадрото на конфликтот или дебатата.\n"
            "2. # Ставови на актерите: За секој клучен актер (личност или институција) наведи:\n"
            "   - Клучна порака или цитат.\n"
            "   - Мотив или интерес (што сакаат да постигнат).\n\n"
            "ПРАВИЛА: Користи БОЛД за имињата. СТРОГО: Не го менувај родот на титулите (пр. не 'Министерката' за машко име). "
            "Не измислувај изјави што ги нема во текстот."
        ),
        "context": (
            "Ти си Главен Уредник и Историчар. Твоја задача е да ја објасниш пошироката слика.\n\n"
            "СТРУКТУРА НА ОДГОВОРОТ:\n"
            "1. # Аналитички контекст: Напиши го ова како сериозна уредничка анализа.\n"
            "2. # Поврзаност со минатото: Објасни како оваа вест се надоврзува на претходни настани (ако се дадени во позадината).\n"
            "3. # Значење и последици: Што значи ова за иднината?\n\n"
            "ПРАВИЛА: Користи префинет новинарски јазик. БОЛД за клучни термини. Без емоџи. "
            "СТРОГО: Не измислувај имиња или настани што не се присутни во материјалите."
        )
    }
    
    system_prompt = prompts.get(mode, prompts["facts"])
    user_prompt = f"АНАЛИЗИРАЈ ГИ СЛЕДНИТЕ СТАТИИ:\n\n{combined_text[:12000]}{history_context}"

    try:
        from ai_engine import sync_call_ai
        # Use mistral for high-quality formatting at low cost
        response, provider = await asyncio.to_thread(
            sync_call_ai,
            prompt=user_prompt,
            system=system_prompt,
            task_type="default",
            max_tokens=1000,
        )
        
        if not response:
            return {"status": "error", "message": "Аналитичарот е зафатен."}

        # Apply final name validation on the report
        from entities import validate_person_names
        response = validate_person_names(response)

        result = {
            "status": "success",
            "report": response,
            "mode": mode,
            "provider": provider
        }
        
        set_cache(cache_key, result, ttl=7200) # Cache for 2 hours
        return result
        
    except Exception as e:
        log.error(f"Analyst Error: {e}", exc_info=True)
        return {"status": "error", "message": "Грешка при анализата."}

@router.get("/intelligence/source-pulse")
async def get_source_pulse():
    from utils import get_source_trust_label, get_source_effective_weight
    sql = """
        WITH first_reporters AS (
            SELECT DISTINCT ON (cluster_id) source, cluster_id
            FROM articles
            ORDER BY cluster_id, created_at ASC
        )
        SELECT 
            a.source,
            AVG(CAST(s.sentiment->'sentiment'->>'score' AS REAL)) as avg_sentiment,
            AVG(CAST(s.sentiment->'tone_analysis'->>'objectivity' AS REAL)) as avg_objectivity,
            AVG(CAST(s.sentiment->'tone_analysis'->>'sensationalism' AS REAL)) as avg_sensationalism,
            COUNT(DISTINCT a.cluster_id) as cluster_count,
            (SELECT COUNT(*) FROM first_reporters fr 
             WHERE fr.source = a.source 
               AND fr.cluster_id IN (SELECT cluster_id FROM articles WHERE created_at >= NOW() - INTERVAL '7 days')
            ) as first_report_count
        FROM cluster_summaries s
        JOIN articles a ON s.cluster_id = a.cluster_id
        WHERE s.sentiment IS NOT NULL AND s.created_at >= NOW() - INTERVAL '7 days'
        GROUP BY a.source HAVING COUNT(DISTINCT a.cluster_id) >= 3
        ORDER BY cluster_count DESC
    """
    rows = await db.async_execute(sql)
    for r in rows:
        r["trust_label"] = get_source_trust_label(r["source"])
        r["effective_weight"] = round(get_source_effective_weight(r["source"]), 2)
        
    return {"status": "success", "data": rows}

@router.get("/intelligence/entity/{name}")
async def get_entity_profile(name: str):
    # Validate name parameter
    name = validate_string_param(name, "name", max_length=200, allow_empty=False)
    
    entity = await db.async_execute_one("SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score FROM knowledge_entities WHERE name = %s", (name,))
    if not entity:
        if not await db.async_execute_one("SELECT 1 FROM cluster_metadata WHERE %s = ANY(tags) LIMIT 1", (name,)):
            raise HTTPException(status_code=404, detail="Entity not found")
        entity = {"name": name, "type": "ENTITY", "total_mentions": 0, "first_seen": None, "last_seen": None, "sentiment_score": 0}
    
    relationships = await db.async_execute("SELECT CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity, weight FROM knowledge_relationships WHERE entity_a = %s OR entity_b = %s ORDER BY weight DESC LIMIT 8", (name, name, name))
    # Use parameterized queries for array contains
    media_stats = await db.async_execute("SELECT a.source, COUNT(DISTINCT a.cluster_id) as mention_count FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE %s = ANY(m.tags) GROUP BY a.source ORDER BY mention_count DESC LIMIT 5", (name,))
    category_stats = await db.async_execute("SELECT a.category, COUNT(DISTINCT a.cluster_id) as count FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE %s = ANY(m.tags) AND a.category IS NOT NULL AND a.category != '' GROUP BY a.category ORDER BY count DESC LIMIT 5", (name,))
    sentiment_history = await db.async_execute("SELECT DATE(a.created_at) as day, AVG(CAST(s.sentiment->'sentiment'->>'score' AS FLOAT)) as avg_sentiment, COUNT(DISTINCT a.cluster_id) as volume FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id JOIN cluster_summaries s ON a.cluster_id = s.cluster_id WHERE %s = ANY(m.tags) AND a.created_at >= NOW() - INTERVAL '14 days' AND s.sentiment IS NOT NULL GROUP BY day ORDER BY day ASC", (name,))
    recent = await db.async_execute("SELECT c.cluster_id, (SELECT title FROM articles WHERE cluster_id = c.cluster_id ORDER BY created_at DESC LIMIT 1) as title, c.updated_at as created_at, s.summary, s.sentiment FROM cluster_metadata c LEFT JOIN cluster_summaries s ON c.cluster_id = s.cluster_id WHERE %s = ANY(c.tags) ORDER BY c.updated_at DESC LIMIT 10", (name,))
    
    processed = []
    for c in recent:
        bullets = [re.sub(r'^[-•*]\s*', '', line).strip() for line in (c["summary"] or "").split('\n') if line.strip() and not line.strip().lower().startswith('статии:')]
        sent = json.loads(c["sentiment"]) if isinstance(c["sentiment"], str) else c["sentiment"]
        processed.append({"cluster_id": c["cluster_id"], "title": cleanAndDecode(c["title"]), "created_at": c["created_at"], "bullets": bullets[:2], "sentiment": sent})

    return {"profile": entity, "related": relationships, "media": media_stats, "categories": category_stats, "sentiment_history": sentiment_history, "clusters": processed}

@router.get("/intelligence/top-entities")
async def get_top_entities(limit: int = 10):
    cache_key = f"api:top-entities:{limit}"
    cached = cached_response(cache_key)
    if cached: return cached
    fetch_limit = max(limit * 6, 40)
    rows = await db.async_execute("SELECT tag AS name, COUNT(*) AS total_mentions FROM (SELECT cm.cluster_id, UNNEST(cm.tags) AS tag FROM cluster_metadata cm JOIN articles a ON a.cluster_id = cm.cluster_id WHERE a.created_at >= NOW() - INTERVAL '48 hours' AND cm.tags IS NOT NULL GROUP BY cm.cluster_id, tag) t GROUP BY tag ORDER BY total_mentions DESC LIMIT %s", (fetch_limit,))
    aggregated = {}
    for row in rows:
        norm = normalize_tag_name(normalize_entity_name(row["name"]))
        if not _is_valid_focus_entity(norm, None): continue
        key = norm.casefold()
        aggregated[key] = {
            "name": norm,
            "type": None,
            "total_mentions": int(aggregated.get(key, {}).get("total_mentions", 0)) + int(row.get("total_mentions") or 0),
        }
    filtered = _compact_focus_entities(list(aggregated.values()), limit=limit)
    set_cache(cache_key, filtered, ttl=600)
    return filtered

@router.get("/intelligence/entity/{name}/topics")
async def get_entity_topics(name: str):
    # Validate name parameter
    name = validate_string_param(name, "name", max_length=200, allow_empty=False)
    return {"status": "success", "data": await db.async_execute("SELECT a.topic, COUNT(*) as count FROM articles a JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id WHERE ce.entity_name = %s AND a.topic IS NOT NULL GROUP BY a.topic ORDER BY count DESC LIMIT 5", (name,))}

@router.get("/intelligence/live-map")
async def get_live_map():
    return {"status": "success", "data": await db.async_execute("SELECT source, COUNT(*) as activity_score FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' GROUP BY source ORDER BY activity_score DESC")}

@router.get("/intelligence/compare-sources")
async def compare_sources(s1: str, s2: str):
    # Validate source names
    s1 = validate_string_param(s1, "s1", max_length=100, allow_empty=False)
    s2 = validate_string_param(s2, "s2", max_length=100, allow_empty=False)
    
    rows = await db.async_execute("SELECT a.source, AVG(CAST(s.sentiment->'sentiment'->>'score' AS REAL)) as avg_sentiment, AVG(CAST(s.sentiment->'tone_analysis'->>'objectivity' AS REAL)) as avg_objectivity, AVG(CAST(s.sentiment->'tone_analysis'->>'sensationalism' AS REAL)) as avg_sensationalism, COUNT(DISTINCT a.cluster_id) as cluster_count FROM cluster_summaries s JOIN articles a ON s.cluster_id = a.cluster_id WHERE a.source = ANY(%s) AND s.sentiment IS NOT NULL AND s.created_at >= NOW() - INTERVAL '30 days' GROUP BY a.source", ([s1, s2],))
    overlap = await db.async_execute_one("WITH src_c AS (SELECT source, cluster_id FROM articles WHERE source = ANY(%s) AND created_at >= NOW() - INTERVAL '30 days' GROUP BY source, cluster_id) SELECT COUNT(*) FILTER (WHERE s1.cluster_id IS NOT NULL AND s2.cluster_id IS NOT NULL) as shared_clusters, COUNT(*) FILTER (WHERE s1.cluster_id IS NOT NULL AND s2.cluster_id IS NULL) as s1_exclusive, COUNT(*) FILTER (WHERE s1.cluster_id IS NULL AND s2.cluster_id IS NOT NULL) as s2_exclusive FROM (SELECT DISTINCT cluster_id FROM src_c WHERE source = %s) s1 FULL OUTER JOIN (SELECT DISTINCT cluster_id FROM src_c WHERE source = %s) s2 ON s1.cluster_id = s2.cluster_id", ([s1, s2], s1, s2))
    return {"status": "success", "data": rows, "overlap": overlap}

@router.post("/intelligence/recommendations")
async def get_personalized_recommendations(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    recent_ids = validate_list_param(payload.get("recentlyRead", []), "recentlyRead", max_items=10, max_item_length=64)
    followed = validate_list_param(payload.get("followedTopics", []), "followedTopics", max_items=10, max_item_length=100)
    limit = min(max(1, int(payload.get("limit", 6))), 20)
    if not recent_ids and not followed: return {"status": "success", "clusters": []}
    user_vectors = []
    if recent_ids:
        rows = await db.async_execute("SELECT embedding FROM articles WHERE cluster_id = ANY(%s) AND embedding IS NOT NULL LIMIT 20", (recent_ids,))
        for r in rows:
            if r["embedding"]: user_vectors.append(json.loads(r["embedding"]) if isinstance(r["embedding"], str) else list(r["embedding"]))
    from embeddings import generate_query_embedding
    for t in followed:
        vec = generate_query_embedding(t)
        if vec: user_vectors.append(vec)
    if not user_vectors: return {"status": "success", "clusters": []}
    import numpy as np
    avg_vec = np.mean(user_vectors, axis=0).tolist()
    results = await db.async_search_semantic(avg_vec, limit=limit * 3)
    seen = set(recent_ids)
    cids = []
    for r in results:
        cid = r.get("cluster_id")
        if cid and cid not in seen:
            cids.append(cid)
            seen.add(cid)
            if len(cids) >= limit: break
    if not cids: return {"status": "success", "clusters": []}
    rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,))
    cmap = {}
    for r in rows: cmap.setdefault(r["cluster_id"], []).append(r)
    formatted = []
    for cid in cids:
        arts = cmap.get(cid, [])
        if not arts: continue
        s_row = await db.async_execute_one("SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cid,))
        m_row = await db.async_execute_one("SELECT representative_image FROM cluster_metadata WHERE cluster_id = %s", (cid,))
        formatted.append({"cluster_id": cid, "articles": arts, "representative_image": m_row["representative_image"] if m_row else None, "score": score_cluster(arts), "has_synthesis": bool(s_row and s_row["summary"]), "is_breaking": any(a.get("is_breaking") for a in arts), "reason": "Предлог за Вас"})
    return {"status": "success", "clusters": formatted}
