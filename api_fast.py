from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging
import datetime
import re
from typing import Optional, List
from collections import defaultdict

from database import db_manager as db
from utils import (
    score_cluster, rank_articles_in_cluster, calculate_reading_time, 
    cached_response, set_cache, is_balanced
)
from ai_engine import PROVIDERS, _call_ai_async, clean_json_response
from prompts import SYNTHESIS_SYSTEM_PROMPT
from config import BREAKING_SCORE_THRESHOLD, API_MAX_PAGE, API_MAX_Q_LEN
from local_nlp import (
    answer_cluster_question_locally,
    generate_daily_brief_fallback,
    normalize_tag_name,
    filter_cluster_tags,
    is_valid_focus_entity,
    build_citation_snippet,
    build_structured_answer_sections,
)

log = logging.getLogger("presek")

app = FastAPI(title="Presek API 6.0", version="6.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _is_valid_focus_entity(name: str, entity_type: Optional[str]) -> bool:
    return is_valid_focus_entity(name, entity_type)


def _parse_perspectives_blob(raw_perspectives) -> list[dict]:
    if not raw_perspectives:
        return []
    if isinstance(raw_perspectives, str):
        try:
            raw_perspectives = json.loads(raw_perspectives)
        except Exception:
            return []
    if not isinstance(raw_perspectives, list):
        return []

    parsed = []
    for item in raw_perspectives:
        if isinstance(item, str):
            content = item.strip()
            if content:
                parsed.append({"angle": "Перспектива", "content": content})
            continue
        if not isinstance(item, dict):
            continue
        angle = str(item.get("angle") or item.get("label") or "Перспектива").strip()
        content = str(item.get("content") or item.get("text") or "").strip()
        if content:
            parsed.append({"angle": angle or "Перспектива", "content": content})
    return parsed


def _default_related_questions(question: str, category: Optional[str]) -> list[str]:
    fallback = [
        "Што е главниот развој во оваа приказна?",
        "Како се разликуваат изворите во известувањето?",
        "Што сè уште не е потврдено?",
    ]
    if category:
        fallback[0] = f"Кој е најважниот развој во темата {str(category).lower()}?"
    return [q for q in fallback if q.strip() and q.strip() != question.strip()][:3]


def _text_terms(text: str) -> set[str]:
    terms = re.findall(r"[A-Za-zА-Яа-яЀ-ӿ0-9]{3,}", (text or "").lower())
    return {
        term for term in terms
        if term not in ENTITY_NOISE_WORDS and term not in {"вести", "вест", "извор", "извори", "кластер"}
    }


def _rank_cluster_citations(question: str, answer: str, articles: list[dict], preferred_numbers: list) -> list[dict]:
    question_terms = _text_terms(question)
    answer_terms = _text_terms(answer)
    combined_terms = question_terms | answer_terms

    preferred_order = []
    for raw in preferred_numbers:
        try:
            idx = int(raw)
        except Exception:
            continue
        if idx not in preferred_order:
            preferred_order.append(idx)

    ranked = []
    for idx, article in enumerate(articles, start=1):
        article_text = " ".join([
            str(article.get("title") or ""),
            str(article.get("description") or ""),
            str(article.get("source") or ""),
        ])
        article_terms = _text_terms(article_text)
        overlap = len(combined_terms & article_terms)
        preferred_bonus = 5 if idx in preferred_order else 0
        title_bonus = 1 if question_terms & _text_terms(str(article.get("title") or "")) else 0
        ranked.append((
            preferred_bonus + overlap + title_bonus,
            -idx,
            {
                "source": article.get("source"),
                "title": article.get("title"),
                "link": article.get("link"),
                "created_at": article.get("created_at"),
                "snippet": build_citation_snippet(article),
            },
        ))

    ranked.sort(reverse=True)
    top = [item[2] for item in ranked if item[0] > 0]
    if top:
        return top[:3]
    return [
        {
            "source": article.get("source"),
            "title": article.get("title"),
            "link": article.get("link"),
            "created_at": article.get("created_at"),
            "snippet": build_citation_snippet(article),
        }
        for article in articles[:2]
    ]

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "6.0.0-async"}

@app.get("/api/intelligence/entity/{name}")
async def get_entity_profile(name: str):
    """Returns detailed profile and relationships for an entity."""
    entity = db.execute_one("""
        SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score
        FROM knowledge_entities WHERE name = %s
    """, (name,))
    
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Get top relationships
    relationships = db.execute("""
        SELECT 
            CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity,
            weight
        FROM knowledge_relationships
        WHERE entity_a = %s OR entity_b = %s
        ORDER BY weight DESC LIMIT 10
    """, (name, name, name))
    
    return {
        "profile": entity,
        "related": relationships
    }

@app.get("/api/intelligence/top-entities")
async def get_top_entities(limit: int = 10):
    """Returns the most mentioned entities."""
    fetch_limit = max(limit * 4, 24)
    rows = db.execute("""
        SELECT name, type, total_mentions 
        FROM knowledge_entities 
        ORDER BY total_mentions DESC LIMIT %s
    """, (fetch_limit,))

    filtered = []
    seen = set()
    for row in rows:
        normalized_name = normalize_tag_name(row["name"])
        if not _is_valid_focus_entity(normalized_name, row.get("type")):
            continue
        dedupe_key = normalized_name.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        filtered.append({
            "name": normalized_name,
            "type": row.get("type"),
            "total_mentions": row.get("total_mentions"),
        })
        if len(filtered) >= limit:
            break

    return filtered

@app.get("/api/news")
async def get_news(
    q: Optional[str] = None,
    category: Optional[str] = None,
    topic: Optional[str] = None,
    entity: Optional[str] = None,
    sort: str = "recent",
    page: int = 0,
    page_size: int = 24
):
    try:
        # Fetch clusters with aggregated entity names
        sql = """
            WITH cluster_ents AS (
                SELECT cluster_id, array_agg(entity_name) as entity_names
                FROM cluster_entities
                GROUP BY cluster_id
            )
            SELECT a.*, COALESCE(ce.entity_names, '{}') as entity_names
            FROM (
        """
        params = []
        if q:
            sql += "SELECT * FROM articles WHERE 1=1 AND (title ILIKE %s OR description ILIKE %s) LIMIT 100"
            params = [f'%{q}%', f'%{q}%']
        elif entity:
            sql += """
                SELECT a.* FROM articles a
                JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id
                WHERE ce.entity_name = %s
                ORDER BY a.created_at DESC LIMIT 100
            """
            params = [entity]
        elif topic:
            sql += "SELECT * FROM articles WHERE topic = %s ORDER BY created_at DESC LIMIT 100"
            params = [topic]
        elif category:
            sql += "SELECT * FROM articles WHERE category = %s ORDER BY created_at DESC LIMIT 100"
            params = [category]
        else:
            sql += "SELECT * FROM articles WHERE country = '🇲🇰' ORDER BY created_at DESC LIMIT 200"

        rows = db.execute(sql + ") a LEFT JOIN cluster_ents ce ON a.cluster_id = ce.cluster_id", tuple(params))

        clusters = defaultdict(list)
        for r in rows:
            r['reading_time'] = calculate_reading_time(r.get('description', ''))
            clusters[r['cluster_id']].append(r)

        ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        
        if sort == 'popular':
            ranked_clusters.sort(key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster, reverse=True)

        start = page * page_size
        paged_clusters = ranked_clusters[start:start + page_size]

        # Fetch metadata and synthesis status
        cid_list = [c[0]["cluster_id"] for c in paged_clusters]
        if cid_list:
            metadata_rows = db.execute(
                "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
                (cid_list,)
            )
            rep_images = {r['cluster_id']: r['representative_image'] for r in metadata_rows}
            
            synthesis_ids = set(db.get_synthesis_ids(cid_list))
        else:
            rep_images = {}
            synthesis_ids = set()

        result = []
        for arts in paged_clusters:
            main = arts[0]
            cid = main["cluster_id"]
            s = score_cluster(arts)
            result.append({
                "cluster_id": cid,
                "articles": arts,
                "representative_image": rep_images.get(cid),
                "reading_time": main.get('reading_time', 1),
                "score": round(s, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_balanced": is_balanced(arts),
                "entities": main.get("entity_names", [])
            })

        return {
            "status": "success",
            "clusters": result,
            "page": page,
            "has_more": len(ranked_clusters) > start + page_size
        }
    except Exception as e:
        log.error(f"FastAPI News Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/api/cluster/{cluster_id}")
async def get_cluster_detail(cluster_id: str):
    """Returns detailed information for a specific cluster."""
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")
        
    try:
        # 1. Fetch articles
        rows = db.execute(
            "SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", 
            (cluster_id,)
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Cluster not found")
            
        articles = rank_articles_in_cluster(rows)
        for a in articles:
            a['reading_time'] = calculate_reading_time(a.get('description', ''))

        # 2. Fetch synthesis and perspectives
        s_row = db.execute_one(
            "SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s", 
            (cluster_id,)
        )
        synthesis = s_row["summary"] if s_row else None
        perspectives = s_row["perspectives"] if s_row and s_row["perspectives"] else []
        if isinstance(perspectives, str):
            perspectives = json.loads(perspectives)

        # 3. Fetch metadata (tags, etc)
        m_row = db.execute_one(
            "SELECT tags, topics FROM cluster_metadata WHERE cluster_id = %s", 
            (cluster_id,)
        )
        tags = filter_cluster_tags(m_row["tags"] if m_row else [])
        topics = m_row["topics"] if m_row else []

        # 4. Related clusters
        related = []
        if tags:
            related_rows = db.execute("""
                SELECT 
                    m.cluster_id, 
                    (SELECT title FROM articles WHERE cluster_id = m.cluster_id ORDER BY created_at DESC LIMIT 1) as title,
                    (SELECT image_url FROM articles WHERE cluster_id = m.cluster_id AND image_url IS NOT NULL ORDER BY created_at DESC LIMIT 1) as image_url
                FROM cluster_metadata m
                WHERE m.cluster_id != %s
                  AND m.updated_at >= NOW() - INTERVAL '48 hours'
                  AND m.tags && %s
                ORDER BY m.updated_at DESC
                LIMIT 4
            """, (cluster_id, tags))
            related = related_rows

        return {
            "status": "success",
            "data": {
                "cluster_id": cluster_id,
                "articles": articles,
                "synthesis": synthesis,
                "perspectives": perspectives,
                "tags": tags,
                "topics": topics,
                "related": related,
                "total_reading_time": sum(a['reading_time'] for a in articles)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"FastAPI Cluster Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cluster detail")


@app.post("/api/cluster/{cluster_id}/ask")
async def ask_cluster(cluster_id: str, request: Request):
    """Answers a question using only the current cluster's context."""
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    question = str((payload or {}).get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    if len(question) > API_MAX_Q_LEN:
        raise HTTPException(status_code=400, detail="Question is too long")

    articles = db.execute(
        """
        SELECT title, description, source, link, created_at, category
        FROM articles
        WHERE cluster_id = %s
        ORDER BY created_at DESC
        LIMIT 8
        """,
        (cluster_id,)
    )
    if not articles:
        raise HTTPException(status_code=404, detail="Cluster not found")

    summary_row = db.execute_one(
        "SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s",
        (cluster_id,)
    )
    synthesis = (summary_row or {}).get("summary") or ""
    perspectives = _parse_perspectives_blob((summary_row or {}).get("perspectives"))

    local_answer = answer_cluster_question_locally(question, articles, synthesis=synthesis, perspectives=perspectives)
    if local_answer:
        sections = build_structured_answer_sections(
            local_answer["answer"],
            articles,
            synthesis=synthesis,
            perspectives=perspectives,
        )
        return {
            "status": "success",
            "answer": local_answer["answer"],
            "citations": _rank_cluster_citations(question, local_answer["answer"], articles, []),
            "related_questions": local_answer["related_questions"][:3],
            "confidence": local_answer["confidence"],
            "confirmed_points": sections["confirmed_points"],
            "unclear_points": sections["unclear_points"],
            "source_differences": sections["source_differences"],
            "generated_locally": True,
        }

    article_context = []
    citation_index = {}
    for idx, article in enumerate(articles, start=1):
        article_context.append(
            f"[{idx}] Извор: {article['source']}\n"
            f"Наслов: {article['title']}\n"
            f"Опис: {(article.get('description') or '').strip()}\n"
        )
        citation_index[idx] = {
            "source": article["source"],
            "title": article["title"],
            "link": article.get("link"),
            "created_at": article.get("created_at"),
        }

    perspective_context = "\n".join(
        f"- {item['angle']}: {item['content']}" for item in perspectives[:4]
    )

    prompt = (
        "Контекст за еден новински кластер:\n\n"
        f"Системско резиме:\n{synthesis or 'Нема достапно резиме.'}\n\n"
        f"Перспективи:\n{perspective_context or 'Нема издвоени перспективи.'}\n\n"
        "Извори:\n"
        + "\n".join(article_context)
        + "\n"
        f"Прашање од корисник: {question}\n\n"
        "Одговори само врз основа на контекстот погоре. Ако нешто не е потврдено или недостига, кажи го тоа јасно. "
        "Врати JSON со полиња: "
        "{\"answer\":\"...\",\"confirmed_points\":[\"...\"],\"unclear_points\":[\"...\"],\"source_differences\":\"...\",\"citation_numbers\":[1,2],\"related_questions\":[\"...\",\"...\",\"...\"],\"confidence\":\"high|medium|low\"}. "
        "Во citation_numbers вклучи само броеви од листата на извори што директно го поддржуваат одговорот. "
        "Одговорот мора да биде на македонски."
    )

    system = (
        "Ти си новинарски асистент за Пресек. Не измислувај факти. "
        "Ако контекстот не е доволен, кажи што не е јасно. Биди прецизен и концизен."
    )

    response_text, _provider = await _call_ai_async(
        prompt,
        system,
        task_type="chat",
        max_tokens=700,
        json_mode=True,
    )

    if not response_text:
        raise HTTPException(status_code=503, detail="Системот не можеше да одговори во моментот")

    parsed = clean_json_response(response_text)
    if isinstance(parsed, dict):
        answer = str(parsed.get("answer") or "").strip()
        confirmed_points = [str(item).strip() for item in parsed.get("confirmed_points") or [] if str(item).strip()]
        unclear_points = [str(item).strip() for item in parsed.get("unclear_points") or [] if str(item).strip()]
        source_differences = str(parsed.get("source_differences") or "").strip()
        citation_numbers = parsed.get("citation_numbers") or []
        related_questions = parsed.get("related_questions") or []
        confidence = str(parsed.get("confidence") or "medium").strip().lower()
    else:
        answer = str(parsed).strip()
        confirmed_points = []
        unclear_points = []
        source_differences = ""
        citation_numbers = [1, 2]
        related_questions = []
        confidence = "medium"

    citations = _rank_cluster_citations(question, answer, articles, citation_numbers)
    sections = build_structured_answer_sections(
        answer,
        articles,
        synthesis=synthesis,
        perspectives=perspectives,
    )
    if not confirmed_points:
        confirmed_points = sections["confirmed_points"]
    if not unclear_points:
        unclear_points = sections["unclear_points"]
    if not source_differences:
        source_differences = sections["source_differences"]

    clean_related = []
    for item in related_questions:
        text = str(item).strip()
        if text and text not in clean_related and text != question:
            clean_related.append(text)

    if not clean_related:
        clean_related = _default_related_questions(question, articles[0].get("category"))

    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"

    return {
        "status": "success",
        "answer": answer,
        "citations": citations[:3],
        "related_questions": clean_related[:3],
        "confidence": confidence,
        "confirmed_points": confirmed_points[:3],
        "unclear_points": unclear_points[:2],
        "source_differences": source_differences,
    }

@app.get("/api/briefing")
async def get_briefing():
    try:
        row = db.execute_one(
            "SELECT date, content FROM daily_briefings WHERE date = CURRENT_DATE"
        )
        if not row:
            row = db.execute_one(
                "SELECT date, content FROM daily_briefings ORDER BY date DESC LIMIT 1"
            )
        if not row:
            fallback_rows = db.execute(
                "SELECT cluster_id, title, description, source, category, topic, created_at "
                "FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC LIMIT 10"
            )
            return {
                "date": datetime.date.today().isoformat(),
                "content": generate_daily_brief_fallback(fallback_rows),
                "generated_locally": True,
            }

        return {
            "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"]),
            "content": row["content"] or ""
        }
    except Exception as e:
        log.error(f"FastAPI Briefing Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch briefing")

@app.get("/api/archive")
async def get_archive(
    date: str = Query(...),
    source: str = "",
    topic: str = "",
    page: int = 0,
    page_size: int = 50
):
    """Return clustered archive data for a specific date."""
    try:
        datetime.datetime.strptime(date, '%Y-%m-%d')

        offset = page * page_size
        where_clauses = ["created_at::date = %s"]
        params = [date]

        if source:
            where_clauses.append("source = %s")
            params.append(source)

        if topic:
            where_clauses.append("topic = %s")
            params.append(topic)

        where_sql = " AND ".join(where_clauses)

        rows = db.execute(
            "SELECT * FROM articles "
            f"WHERE {where_sql} "
            "ORDER BY created_at DESC LIMIT 1500",
            tuple(params)
        )

        clusters = defaultdict(list)
        for row in rows:
            row["reading_time"] = calculate_reading_time(row.get("description", ""))
            clusters[row["cluster_id"]].append(row)

        ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        ranked_clusters.sort(key=score_cluster, reverse=True)

        paged_clusters = ranked_clusters[offset: offset + page_size]
        cluster_ids = [cluster[0]["cluster_id"] for cluster in paged_clusters]
        synthesis_ids = set(db.get_synthesis_ids(cluster_ids)) if cluster_ids else set()
        metadata_rows = db.execute(
            "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
            (cluster_ids or [""],)
        ) if cluster_ids else []
        rep_images = {r["cluster_id"]: r["representative_image"] for r in metadata_rows}

        cluster_payload = []
        for arts in paged_clusters:
            cid = arts[0]["cluster_id"]
            s = score_cluster(arts)
            cluster_payload.append({
                "cluster_id": cid,
                "articles": arts,
                "representative_image": rep_images.get(cid),
                "reading_time": arts[0].get("reading_time", 1),
                "score": round(s, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_balanced": is_balanced(arts),
            })

        total = db.execute_one(
            f"SELECT COUNT(*) FROM articles WHERE {where_sql}",
            tuple(params)
        )["count"]
        sources = db.execute_one(
            f"SELECT COUNT(DISTINCT source) FROM articles WHERE {where_sql}",
            tuple(params)
        )["count"]
        top_sources = db.execute(
            f"SELECT source, COUNT(*) AS n FROM articles WHERE {where_sql} "
            "GROUP BY source ORDER BY n DESC LIMIT 8",
            tuple(params)
        )
        top_topics = db.execute(
            f"SELECT topic, COUNT(*) AS n FROM articles WHERE {where_sql} "
            "GROUP BY topic ORDER BY n DESC LIMIT 8",
            tuple(params)
        )

        return {
            "clusters": cluster_payload,
            "total": total,
            "sources": sources,
            "date": date,
            "source": source,
            "topic": topic,
            "page": page,
            "page_size": page_size,
            "has_more": offset + page_size < len(ranked_clusters),
            "total_clusters": len(ranked_clusters),
            "top_sources": [dict(r) for r in top_sources],
            "top_topics": [dict(r) for r in top_topics],
        }
    except Exception as e:
        log.error(f"FastAPI Archive Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/stats")
async def get_stats():
    try:
        return {"status": "success", "data": db.get_stats()}
    except Exception as e:
        log.error(f"FastAPI Stats Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

@app.get("/api/stats/full")
async def get_stats_full():
    try:
        cached = cached_response("stats:full", ttl=120)
        if cached:
            return cached

        total = db.execute_one("SELECT COUNT(*) FROM articles")["count"] or 0
        last_24h = db.execute_one(
            "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )["count"] or 0
        summarized = db.execute_one(
            "SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''"
        )["count"] or 0
        summarized_pct = round((summarized / total * 100), 1) if total else 0

        db_size_row = db.execute_one(
            "SELECT ROUND(pg_database_size(current_database()) / 1048576.0, 1) AS mb"
        )
        db_size_mb = float(db_size_row["mb"]) if db_size_row else 0

        total_feeds = db.execute_one(
            "SELECT COUNT(DISTINCT source) AS n FROM articles"
        )["n"] or 0

        dates_row = db.execute_one(
            "SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest FROM articles"
        )
        oldest_article = dates_row["oldest"].isoformat() if dates_row and dates_row["oldest"] else None
        newest_article = dates_row["newest"].isoformat() if dates_row and dates_row["newest"] else None

        by_source = db.execute(
            "SELECT source, COUNT(*) AS n FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "AND (country = '🇲🇰' OR country IS NULL OR country = '') "
            "GROUP BY source ORDER BY n DESC LIMIT 10"
        )

        by_category = [
            {"cat": r["category"] or "Друго", "n": r["n"]}
            for r in db.execute(
                "SELECT category, COUNT(*) AS n FROM articles GROUP BY category ORDER BY n DESC LIMIT 8"
            )
        ]

        velocity = db.execute(
            "SELECT date_trunc('hour', created_at) AS t, COUNT(*) AS n "
            "FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "GROUP BY t ORDER BY t"
        )
        velocity_out = [{"t": r["t"].isoformat(), "n": r["n"]} for r in velocity]

        speed_leaderboard = db.execute(
            "SELECT source, COUNT(*) AS first_count FROM ("
            "  SELECT DISTINCT ON (cluster_id) cluster_id, source "
            "  FROM articles WHERE created_at >= NOW() - INTERVAL '7 days' "
            "  AND (country = '🇲🇰' OR country IS NULL OR country = '') "
            "  ORDER BY cluster_id, created_at ASC"
            ") first_articles GROUP BY source ORDER BY first_count DESC LIMIT 8"
        )

        result = {
            "total_articles": total,
            "last_24h": last_24h,
            "summarized_pct": summarized_pct,
            "uptime": "Online",
            "db_size_mb": db_size_mb,
            "total_feeds": total_feeds,
            "oldest_article": oldest_article,
            "new_article": newest_article,
            "by_source": [{"source": r["source"], "n": r["n"]} for r in by_source],
            "by_category": by_category,
            "velocity": velocity_out,
            "speed_leaderboard": [{"source": r["source"], "first_count": r["first_count"]} for r in speed_leaderboard],
            "sentiment_index": []
        }

        set_cache("stats:full", result, ttl=120)
        return result

    except Exception as e:
        log.error(f"FastAPI Stats Full Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

@app.get("/api/sources")
async def get_sources():
    """Return all known sources from articles."""
    try:
        rows = db.execute(
            "SELECT DISTINCT source, country, category FROM articles ORDER BY source ASC"
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"FastAPI Sources Error: {e}")
        return []

@app.get("/api/sources/pulse")
async def get_sources_pulse():
    """Return top MK sources by article count in last 24h."""
    try:
        rows = db.execute(
            "SELECT source, COUNT(*) as n FROM articles "
            "WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "AND (country = '🇲🇰' OR country IS NULL OR country = '') "
            "GROUP BY source ORDER BY n DESC LIMIT 10"
        )
        return [{"source": r["source"], "count": r["n"]} for r in rows]
    except Exception as e:
        log.warning(f"FastAPI Pulse Error: {e}")
        return []

@app.get("/api/chat/stream")
async def chat_stream(cluster_id: str, query: str):
    """Streams AI response for a specific cluster."""
    
    # 1. Get cluster context
    articles = db.execute("SELECT title, description, source FROM articles WHERE cluster_id = %s LIMIT 10", (cluster_id,))
    if not articles:
        raise HTTPException(status_code=404, detail="Cluster not found")
    
    context = "\n".join([f"- [{a['source']}]: {a['title']}" for a in articles])

    async def generate():
        try:
            full_prompt = f"Context:\n{context}\n\nUser Question: {query}"
            generator = await _call_ai_async(full_prompt, SYNTHESIS_SYSTEM_PROMPT, task_type="chat", stream=True)
            if generator:
                async for chunk in generator:
                    if chunk:
                        yield f"data: {json.dumps({'token': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/trending")
async def get_trending():
    from trending import get_trending
    words = get_trending(limit=20)
    return words
