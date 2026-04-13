import json
import logging
import re
from typing import Optional, List
from collections import defaultdict
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from database import db_manager as db
from utils import (
    score_cluster, rank_articles_in_cluster, calculate_reading_time, 
    cached_response, set_cache, is_balanced, assess_cluster_synthesis_freshness,
    annotate_cluster_articles, score_cluster_for_homepage,
    event_stream, record_runtime_event,
)
from ai_engine import PROVIDERS, _call_ai_async, clean_json_response
from config import (
    BREAKING_SCORE_THRESHOLD,
    API_MAX_PAGE,
    API_MAX_Q_LEN,
)
from local_nlp import (
    answer_cluster_question_locally,
    filter_cluster_tags,
    build_citation_snippet,
    build_structured_answer_sections,
)
from api_helpers import (
    normalize_perspectives as _parse_perspectives_blob,
    default_related_questions as _default_related_questions,
    related_questions_from_context as _related_questions_from_context,
    rank_cluster_citations as _rank_cluster_citations,
)
from .common import cleanAndDecode, _news_row_limit

log = logging.getLogger("presek")
router = APIRouter()

def _fallback_citations(articles) -> list[dict]:
    return [
        {
            "source": article.get("source"),
            "title": article.get("title"),
            "link": article.get("link"),
            "created_at": article.get("created_at"),
            "snippet": build_citation_snippet(article),
        }
        for article in (articles or [])[:2]
    ]

def _safe_rank_cluster_citations(question: str, answer: str, articles, citation_numbers) -> list[dict]:
    try:
        return _rank_cluster_citations(question, answer, articles, citation_numbers)
    except Exception as e:
        log.warning(f"[routes news] citation ranking failed: {e}", exc_info=True)
        return _fallback_citations(articles)

def _build_cluster_answer_fallback(question: str, articles, synthesis: str = "", perspectives=None) -> dict:
    articles = [dict(article) if not isinstance(article, dict) else article for article in (articles or [])]
    category = articles[0].get("category") if articles else None
    perspectives = _parse_perspectives_blob(perspectives or [])
    local_answer = None

    try:
        local_answer = answer_cluster_question_locally(
            question,
            articles,
            synthesis=synthesis,
            perspectives=perspectives,
        )
    except Exception as e:
        log.warning(f"[routes news] local helper failed: {e}")

    if not local_answer and articles:
        lead = articles[0]
        lead_title = str(lead.get("title") or "Оваа приказна")
        lead_source = str(lead.get("source") or "Извор").strip()
        local_answer = {
            "answer": f"Најважното во овој момент е: {lead_title}. Водечкиот достапен извор во овој кластер е {lead_source}.",
            "citations": articles[:2],
            "related_questions": _default_related_questions(question, category),
            "confidence": "low",
        }

    sections = {
        "confirmed_points": [],
        "unclear_points": [],
        "source_differences": "",
    }
    try:
        sections = build_structured_answer_sections(
            local_answer["answer"] if local_answer else "",
            articles,
            synthesis=synthesis,
            perspectives=perspectives,
        )
    except Exception as e:
        log.warning(f"[routes news] section builder failed during fallback: {e}")

    citations = _safe_rank_cluster_citations(question, local_answer["answer"] if local_answer else "", articles, [])

    return {
        "status": "success",
        "answer": (local_answer or {}).get("answer", "Во моментов системот не може да даде подетален одговор."),
        "citations": citations,
        "related_questions": (local_answer or {}).get("related_questions") or _related_questions_from_context(
            question,
            category,
            has_perspectives=bool(perspectives),
            has_multiple_sources=len(articles) >= 2,
            has_unclear_points=bool(sections.get("unclear_points")),
        ),
        "confidence": (local_answer or {}).get("confidence", "low"),
        "confirmed_points": sections.get("confirmed_points", [])[:3],
        "unclear_points": sections.get("unclear_points", [])[:2],
        "source_differences": sections.get("source_differences", ""),
        "generated_locally": True,
    }

async def _build_cluster_answer_payload(cluster_id: str, question: str) -> dict:
    if cluster_id != "frontpage" and not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    if len(question) > API_MAX_Q_LEN:
        raise HTTPException(status_code=400, detail="Question is too long")

    if cluster_id == "frontpage":
        try:
            frontpage_articles = db.execute(
                """
                SELECT a.title, a.source, a.category, a.link
                FROM cluster_metadata m
                JOIN articles a ON m.cluster_id = a.cluster_id
                WHERE m.updated_at >= NOW() - INTERVAL '24 hours'
                ORDER BY m.updated_at DESC
                LIMIT 30
                """
            )
            context_lines = []
            for idx, a in enumerate(frontpage_articles, start=1):
                context_lines.append(f"[{idx}] {a['source']} ({a['category']}): {a['title']}")
                
            prompt = (
                "Ова се најновите вести од насловната страница на македонскиот агрегатор Пресек:\n\n"
                f"{chr(10).join(context_lines)}\n\n"
                f"Прашање од корисник: {question}\n\n"
                "Одговори генерално врз основа на овие вести. Ако корисникот прашува за трендови, сумирај ги најважните. "
                "Врати JSON со полиња: "
                "{\"answer\":\"...\",\"confirmed_points\":[\"...\"],\"unclear_points\":[\"...\"],\"source_differences\":\"...\",\"citation_numbers\":[1,2],\"related_questions\":[\"...\",\"...\"],\"confidence\":\"high|medium|low\"}. "
                "Одговорот мора да биде на македонски."
            )
            system = "Ти си интелигентен новинарски асистент. Анализирај го глобалниот контекст на вестите и одговарај прецизно."
            
            response_text, provider = await _call_ai_async(prompt, system, task_type="chat", max_tokens=700, json_mode=True)
            if not response_text:
                raise ValueError("No AI response")
                
            data = clean_json_response(response_text)
            if not isinstance(data, dict):
                data = {"answer": str(data)}
            record_runtime_event("chat_path", mode=provider or "unknown", surface="frontpage_answer")
            
            citations = []
            if isinstance(data.get("citation_numbers"), list):
                for idx in data["citation_numbers"]:
                    try:
                        i = int(idx) - 1
                        if 0 <= i < len(frontpage_articles):
                            a = frontpage_articles[i]
                            citations.append({
                                "source": a["source"],
                                "title": a["title"],
                                "link": a["link"],
                                "snippet": a["category"]
                            })
                    except (ValueError, TypeError):
                        pass
                        
            return {
                "status": "success",
                "answer": data.get("answer", "Не можев да генерирам одговор за насловната страница."),
                "citations": citations[:4],
                "related_questions": data.get("related_questions", [])[:3],
                "confidence": data.get("confidence", "medium"),
                "confirmed_points": data.get("confirmed_points", [])[:3],
                "unclear_points": data.get("unclear_points", [])[:2],
                "source_differences": data.get("source_differences", ""),
                "generated_locally": False,
            }
        except Exception as e:
            log.warning(f"[routes news] frontpage answer failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to process frontpage query")

    try:
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
        articles = [dict(article) if not isinstance(article, dict) else article for article in articles]
        if not articles:
            raise HTTPException(status_code=404, detail="Cluster not found")

        synthesis = ""
        perspectives = []
        try:
            summary_row = db.execute_one(
                "SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s",
                (cluster_id,)
            )
            if summary_row:
                synthesis = summary_row.get("summary") or ""
                perspectives = _parse_perspectives_blob(summary_row.get("perspectives"))

            local_answer = answer_cluster_question_locally(question, articles, synthesis=synthesis, perspectives=perspectives)
        except Exception as e:
            log.warning(f"[routes news] local/db setup failed for {cluster_id}: {e}")
            return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
        
        if local_answer:
            sections = build_structured_answer_sections(local_answer["answer"], articles, synthesis=synthesis, perspectives=perspectives)
            return {
                "status": "success",
                "answer": local_answer.get("answer", ""),
                "citations": _safe_rank_cluster_citations(question, local_answer.get("answer", ""), articles, [])[:3],
                "related_questions": list(local_answer.get("related_questions") or [])[:3],
                "confidence": local_answer.get("confidence", "medium"),
                "confirmed_points": sections["confirmed_points"],
                "unclear_points": sections["unclear_points"],
                "source_differences": sections["source_differences"],
                "generated_locally": True,
            }

        article_context = []
        for idx, article in enumerate(articles, start=1):
            article_context.append(f"[{idx}] Извор: {article['source']}\nНаслов: {article['title']}\nОпис: {(article.get('description') or '').strip()}\n")

        perspective_context = "\n".join(f"- {item['angle']}: {item['content']}" for item in perspectives[:4])

        prompt = (
            "Контекст за еден новински кластер:\n\n"
            f"Системско резиме:\n{synthesis or 'Нема достапно резиме.'}\n\n"
            f"Перспективи:\n{perspective_context or 'Нема издвоени перспективи.'}\n\n"
            "Извори:\n" + "\n".join(article_context) + "\n"
            f"Прашање од корисник: {question}\n\n"
            "Врати JSON со полиња: {\"answer\":\"...\",\"confirmed_points\":[\"...\"],\"unclear_points\":[\"...\"],\"source_differences\":\"...\",\"citation_numbers\":[1,2],\"related_questions\":[\"...\",\"...\"],\"confidence\":\"high|medium|low\"}."
        )

        system = "Ти си новинарски асистент за Пресек. Биди прецизен и концизен. Одговарај на македонски."
        response_text, provider = await _call_ai_async(prompt, system, task_type="chat", max_tokens=700, json_mode=True)
        if not response_text:
            return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
        
        record_runtime_event("chat_path", mode=provider or "unknown", surface="cluster_answer")
        parsed = clean_json_response(response_text)
        
        if not isinstance(parsed, dict):
            # Fallback for plain text response
            return {
                "status": "success",
                "answer": str(parsed or response_text).strip(),
                "citations": [],
                "related_questions": [],
                "confidence": "medium",
                "confirmed_points": [],
                "unclear_points": [],
                "source_differences": "",
            }

        answer = str(parsed.get("answer") or "").strip()
        sections = build_structured_answer_sections(answer, articles, synthesis=synthesis, perspectives=perspectives)
        
        return {
            "status": "success",
            "answer": answer,
            "citations": _safe_rank_cluster_citations(question, answer, articles, parsed.get("citation_numbers", []))[:3],
            "related_questions": parsed.get("related_questions", [])[:3],
            "confidence": parsed.get("confidence", "medium"),
            "confirmed_points": parsed.get("confirmed_points", []) or sections["confirmed_points"],
            "unclear_points": parsed.get("unclear_points", []) or sections["unclear_points"],
            "source_differences": parsed.get("source_differences", "") or sections["source_differences"],
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[routes news] unexpected error: {e}", exc_info=True)
        return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)

@router.get("/api/news")
async def get_news(
    q: Optional[str] = None,
    category: Optional[str] = None,
    topic: Optional[str] = None,
    entity: Optional[str] = None,
    sort: str = "recent",
    page: int = 0,
    page_size: int = 24
):
    cache_key = f"api:news:{q}:{category}:{topic}:{entity}:{sort}:{page}:{page_size}"
    cached = cached_response(cache_key)
    if cached: return cached

    try:
        page = max(0, min(int(page or 0), API_MAX_PAGE))
        page_size = max(1, min(int(page_size or 24), 50))
        row_limit = _news_row_limit(page, page_size)
        if q: q = q.strip()[:API_MAX_Q_LEN]

        if q:
            from embeddings import generate_query_embedding
            query_vec = generate_query_embedding(q)
            rows = db.hybrid_search(q, query_vec, limit=row_limit) if query_vec else db.search_articles(q, limit=row_limit)
        elif entity:
            rows = db.execute("SELECT a.* FROM articles a JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id WHERE ce.entity_name = %s ORDER BY a.created_at DESC LIMIT %s", (entity, row_limit))
        elif topic:
            rows = db.execute("SELECT * FROM articles WHERE topic = %s ORDER BY created_at DESC LIMIT %s", (topic, row_limit))
        elif category:
            rows = db.execute("SELECT * FROM articles WHERE category = %s ORDER BY created_at DESC LIMIT %s", (category, row_limit))
        else:
            rows = db.execute("SELECT * FROM articles ORDER BY created_at DESC LIMIT %s", (row_limit,))

        clusters = defaultdict(list)
        cluster_relevance = {}
        for r in rows:
            r['reading_time'] = calculate_reading_time(r.get('description', ''))
            cid = r['cluster_id']
            clusters[cid].append(r)
            # Track best relevance score for this cluster if searching
            if q:
                score = float(r.get('match_score', 0)) + float(r.get('rank', 0))
                if cid not in cluster_relevance or score > cluster_relevance[cid]:
                    cluster_relevance[cid] = score

        ranked_clusters = [annotate_cluster_articles(arts) for arts in clusters.values()]
        if sort == 'popular':
            ranked_clusters.sort(key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        elif q and sort == 'recent':
            # Relevance-first for search results
            ranked_clusters.sort(key=lambda arts: cluster_relevance.get(arts[0]['cluster_id'], 0), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster_for_homepage, reverse=True)

        start = page * page_size
        paged_clusters = ranked_clusters[start:start + page_size]
        cid_list = [c[0]["cluster_id"] for c in paged_clusters]
        rep_images = {r['cluster_id']: r['representative_image'] for r in db.execute("SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)", (cid_list,))} if cid_list else {}
        synthesis_ids = set(db.get_synthesis_ids(cid_list)) if cid_list else set()

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
                "homepage_score": round(score_cluster_for_homepage(arts), 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_fact_check": any(a.get("is_fact_check") for a in arts),
                "has_balanced": is_balanced(arts),
                "entities": main.get("entity_names", [])
            })

        final_response = {"status": "success", "clusters": result, "page": page, "has_more": len(ranked_clusters) > start + page_size}
        set_cache(cache_key, final_response, ttl=180)
        return final_response
    except Exception as e:
        log.error(f"News Route Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": "Internal server error"})

@router.get("/api/cluster/{cluster_id}")
async def get_cluster_detail(cluster_id: str):
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")
    try:
        rows = db.execute("SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", (cluster_id,))
        if not rows: raise HTTPException(status_code=404, detail="Cluster not found")
        articles = annotate_cluster_articles(rows)
        for a in articles: a['reading_time'] = calculate_reading_time(a.get('description', ''))

        s_row = db.execute_one("SELECT summary, generated_article, perspectives, created_at, sentiment, verification_report FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,))
        synthesis = s_row["summary"] if s_row else None
        generated_article = s_row["generated_article"] if s_row else None
        
        def _parse_maybe_json(val):
            if not val: return None
            if isinstance(val, (dict, list)): return val
            try: return json.loads(val)
            except: return None

        sentiment = _parse_maybe_json(s_row["sentiment"]) if s_row else None
        verification_report = _parse_maybe_json(s_row["verification_report"]) if s_row else None
        ai_summary_bullets = [re.sub(r'^[-•*]\s*', '', line).strip() for line in synthesis.split('\n') if line.strip() and not line.strip().lower().startswith('статии:')] if synthesis else []
        perspectives = _parse_maybe_json(s_row["perspectives"]) if s_row else []
        if not perspectives: perspectives = []
        freshness = assess_cluster_synthesis_freshness(articles, (s_row or {}).get("created_at"))

        m_row = db.execute_one("SELECT tags, topics FROM cluster_metadata WHERE cluster_id = %s", (cluster_id,))
        tags = filter_cluster_tags(m_row["tags"] if m_row else [])
        topics = m_row["topics"] if m_row else []

        related = []
        lead_article = articles[0]
        if lead_article.get("embedding"):
            lead_vec = json.loads(lead_article["embedding"]) if isinstance(lead_article["embedding"], str) else list(lead_article["embedding"])
            related_results = db.search_semantic(lead_vec, limit=8)
            related_cids = []
            seen = {cluster_id}
            for r in related_results:
                cid = r.get("cluster_id")
                if cid and cid not in seen:
                    related_cids.append(cid)
                    seen.add(cid)
                    if len(related_cids) >= 4: break
            if related_cids:
                r_rows = db.execute("SELECT a.*, COALESCE(m.tags, '{}') as cluster_tags FROM articles a LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE a.cluster_id = ANY(%s)", (related_cids,))
                r_grouped = defaultdict(list)
                for r in r_rows: r_grouped[r["cluster_id"]].append(r)
                for cid in related_cids:
                    arts = r_grouped.get(cid)
                    if arts:
                        main = annotate_cluster_articles(arts)[0]
                        related.append({"cluster_id": cid, "title": main["title"], "image_url": main.get("image_url"), "tags": filter_cluster_tags(main.get("cluster_tags", [])), "relationship_label": "Сродна тема"})

        chrono = sorted(articles, key=lambda x: x['created_at'])
        timeline = []
        for i, a in enumerate(chrono):
            is_major = (a.get('source_signal') or {}).get('trust_level', 0) >= 0.8
            milestone = "ПОЧЕТОК" if i == 0 else ("КОНСЕНЗУС" if i == len(chrono)-1 and len(chrono)>=3 else "РАЗВОЈ")
            timeline.append({"article_id": a['id'], "title": cleanAndDecode(a['title']), "source": a['source'], "created_at": a['created_at'], "is_first": i == 0, "is_major": is_major, "milestone": milestone})

        return {"status": "success", "data": {"cluster_id": cluster_id, "articles": articles, "timeline": timeline, "synthesis": synthesis, "generated_article": generated_article, "sentiment": sentiment, "verification_report": verification_report, "ai_summary_bullets": ai_summary_bullets, "synthesis_updated_at": freshness["synthesis_updated_at"], "synthesis_freshness": freshness, "perspectives": perspectives, "tags": tags, "topics": topics, "related": related, "total_reading_time": sum(a['reading_time'] for a in articles)}}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Cluster Detail Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/api/cluster/{cluster_id}/ask")
async def ask_cluster_route(cluster_id: str, request: Request):
    from utils import AI_QUERY_MAX_LENGTH
    payload = await request.json()
    q = str(payload.get("question", "")).strip()
    if not q or len(q) > AI_QUERY_MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"Прашањето мора да биде 1–{AI_QUERY_MAX_LENGTH} знаци.")
    return await _build_cluster_answer_payload(cluster_id, q)

@router.post("/api/chat_cluster")
async def chat_cluster_route(request: Request):
    from utils import AI_QUERY_MAX_LENGTH
    payload = await request.json()
    q = str(payload.get("query", "")).strip()
    if not q or len(q) > AI_QUERY_MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"Прашањето мора да биде 1–{AI_QUERY_MAX_LENGTH} знаци.")
    return await _build_cluster_answer_payload(str(payload.get("cluster_id", "")).strip(), q)

@router.get("/api/live")
async def get_live_route():
    return StreamingResponse(event_stream("updates"), media_type="text/event-stream")
