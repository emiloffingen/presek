import datetime
import json
import asyncio
import logging
import re
import hashlib
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Request, HTTPException

from database import db_manager as db
from embeddings import generate_query_embedding
from utils import cached_response, set_cache, score_cluster
from nlp import normalize_tag_name
from entities import normalize_entity_name, normalize_person_surface_name
from .common import cleanAndDecode, _is_valid_focus_entity
from .security import validate_cluster_id, validate_list_param, validate_string_param
from limiter import custom_rate_limit
from ai_engine import sync_call_ai, clean_json_response
from prompts import RESEARCH_SYSTEM_PROMPT

log = logging.getLogger("presek")
router = APIRouter()


class PulseVelocity(BaseModel):
    t: datetime.datetime
    n: int


class PulseCategory(BaseModel):
    category: str
    n: int


class GlobalPulseResponse(BaseModel):
    status: str
    timestamp: datetime.datetime
    last_24h: int
    velocity: List[PulseVelocity]
    by_category: List[PulseCategory]
    by_topic_sentiment: List[Dict[str, Any]] = []
    intelligence: Dict[str, Any]
    top_entities: List[Dict[str, Any]] = []


_FRESHNESS_EXPR = "COALESCE(ingested_at, created_at)"
_CASE_INSENSITIVE_TAG_EXISTS = "EXISTS (SELECT 1 FROM unnest(COALESCE(m.tags, '{}')) AS tag WHERE LOWER(tag) = LOWER(%s))"

_RESEARCH_MODE_QUERIES = {
    "facts": (
        "Izvleci im najvaznite brojki, datumi, fakti i vremenska ramka od ova prica. "
        "Ne dodavaj brojki sto ne postojat vo kontekstot."
    ),
    "perspectives": (
        "Identifikuvaj im klucnite akteri, nivnite stavovi, izjavi i razlicnite agli vo prikaznata. "
        "Ne izmisluvaj izjavi sto ne se vo kontekstot."
    ),
    "context": (
        "Objasni ga posirokiot kontekst, prethodnite povrzani slucuvanja i moznite posledice od ova prica. "
        "Jasno oddeli sto e vo izvorite od analitickata ramka."
    ),
}

_RESEARCH_MODE_LABELS = {
    "facts": "Fakti i podatoci",
    "perspectives": "Perspektivi i izjavi",
    "context": "Kontekstualna ramka",
    "custom": "odgovor na istrazuvanjeto",
}

_FOCUS_ENTITY_GENERIC_SINGLE_WORDS = {
    "dogovor",
    "tesnec",
    "reakcije",
    "odluka",
    "merki",
    "izbori",
}


async def _build_gemma_research_context(
    cluster_id: str, mode: str = "custom", query: str = ""
) -> tuple[str, list[str]]:
    if mode == "custom" and query:
        # Generate embedding for the query if we have the cache mechanism or rely on basic full text / vector search if possible.
        # However, to avoid slowing down with synchronous embedding calls here, we'll fetch more articles and let the LLM handle semantic relevance within a larger context.
        articles = await db.async_execute(
            """
            SELECT title, full_content, source, embedding, created_at
            FROM articles
            WHERE cluster_id = %s
            ORDER BY COALESCE(ingested_at, created_at) DESC
            LIMIT 20
        """,
            (cluster_id,),
        )
    else:
        articles = await db.async_execute(
            """
            SELECT title, full_content, source, embedding, created_at
            FROM articles
            WHERE cluster_id = %s
            ORDER BY COALESCE(ingested_at, created_at) DESC
            LIMIT 20
        """,
            (cluster_id,),
        )

    if not articles:
        raise HTTPException(status_code=404, detail="Klasterot ne e pronajden")

    summary_row = await db.async_execute_one(
        """
        SELECT summary, generated_article, verification_report, perspectives
        FROM cluster_summaries
        WHERE cluster_id = %s
    """,
        (cluster_id,),
    )

    parts = []
    if summary_row:
        if summary_row.get("summary"):
            parts.append(f"UREDNICKO rezime:\n{summary_row['summary']}")
        if summary_row.get("generated_article"):
            parts.append(f"SINTEZA:\n{summary_row['generated_article']}")
        if summary_row.get("verification_report"):
            try:
                vr = (
                    json.loads(summary_row["verification_report"])
                    if isinstance(summary_row["verification_report"], str)
                    else summary_row["verification_report"]
                )
                parts.append(
                    f"PROVERKA NA FAKTI (Sistemska analiza):\n{json.dumps(vr, ensure_ascii=False, indent=2)}"
                )
            except Exception as e:
                log.debug(f"Failed to parse verification_report JSON: {e}")
        if summary_row.get("perspectives"):
            try:
                pers = (
                    json.loads(summary_row["perspectives"])
                    if isinstance(summary_row["perspectives"], str)
                    else summary_row["perspectives"]
                )
                parts.append(
                    f"MEDIUMSKI PERSPEKTIVI (Sistemska analiza):\n{json.dumps(pers, ensure_ascii=False, indent=2)}"
                )
            except Exception as e:
                log.debug(f"Failed to parse perspectives JSON: {e}")

    sources = []
    for article in articles:
        source = str(article.get("source") or "Nepoznat izvor").strip()
        if source and source not in sources:
            sources.append(source)
        text = article.get("full_content") or article.get("title") or ""
        parts.append(
            f"--- izvor: {source} ({article['created_at'].strftime('%H:%M %d.%m.%Y')}) ---\n{text}"
        )

    if mode == "context":
        try:
            import numpy as np

            vecs = [
                (
                    json.loads(a["embedding"])
                    if isinstance(a.get("embedding"), str)
                    else list(a["embedding"])
                )
                for a in articles
                if a.get("embedding")
            ]
            if vecs:
                avg_vec = np.mean(vecs, axis=0).tolist()
                vec_str = "[" + ",".join(map(str, avg_vec)) + "]"
                past_events = await db.async_execute(
                    """
                    SELECT title, created_at
                    FROM articles
                    WHERE embedding IS NOT NULL AND cluster_id != %s
                      AND created_at < NOW() - INTERVAL '24 hours'
                    ORDER BY (embedding <=> %s::vector) ASC
                    LIMIT 10
                """,
                    (cluster_id, vec_str),
                )
                if past_events:
                    history_list = "\n".join(
                        [
                            f"- {p['title']} ({p['created_at'].strftime('%d.%m.%Y')})"
                            for p in past_events
                        ]
                    )
                    parts.append(
                        f"POVRZANI PRETHODNI NASTANI OD BAZATA:\n{history_list}"
                    )
        except Exception as e:
            log.warning(f"Failed to fetch Gemma research history context: {e}")

    return "\n\n".join(parts)[:45000], sources


def _compact_focus_entities(items: list[dict], limit: int) -> list[dict]:
    by_key = {
        str(item.get("name") or "").casefold(): dict(item)
        for item in items
        if str(item.get("name") or "").strip()
    }

    # Merge common fragmented geopolitics phrase into one canonical entity.
    if "ormuz" in by_key and "tesnec" in by_key:
        merged_mentions = max(
            int(by_key.get("ormuz", {}).get("total_mentions") or 0),
            int(by_key.get("tesnec", {}).get("total_mentions") or 0),
            int(by_key.get("ormuski tesnec", {}).get("total_mentions") or 0),
        )
        by_key["ormuski tesnec"] = {
            "name": "Ormuski Tesnec",
            "type": by_key.get("ormuski tesnec", {}).get("type") or "LOC",
            "total_mentions": merged_mentions,
        }
        by_key.pop("ormuz", None)
        by_key.pop("tesnec", None)

    compact = []
    # Sort and take top N without further destructive processing
    for item in sorted(
        by_key.values(),
        key=lambda entry: int(entry.get("total_mentions") or 0),
        reverse=True,
    ):
        compact.append(item)
        if len(compact) >= limit:
            break
    return compact


@router.get("/intelligence/pulse-overview")
async def get_pulse_overview():
    """Provides a high-level summary of the media landscape (free, token-less)."""
    cache_key = "api:intelligence:pulse-overview"
    cached = cached_response(cache_key)
    if cached:
        return cached

    # 1. Trending Entities (Last 48h)
    trending = await db.async_execute(
        """
        SELECT name, total_mentions, sentiment_score, type
        FROM knowledge_entities
        WHERE last_seen >= NOW() - INTERVAL '48 hours'
        ORDER BY total_mentions DESC
        LIMIT 10
    """
    )

    # 2. Sentiment Extremes
    positives = await db.async_execute(
        """
        SELECT name, sentiment_score
        FROM knowledge_entities
        WHERE total_mentions >= 5 AND last_seen >= NOW() - INTERVAL '7 days'
        ORDER BY sentiment_score DESC
        LIMIT 5
    """
    )

    negatives = await db.async_execute(
        """
        SELECT name, sentiment_score
        FROM knowledge_entities
        WHERE total_mentions >= 5 AND last_seen >= NOW() - INTERVAL '7 days'
        ORDER BY sentiment_score ASC
        LIMIT 5
    """
    )

    # 3. Hot Relationships (Duos)
    relationships = await db.async_execute(
        """
        SELECT entity_a, entity_b, weight
        FROM knowledge_relationships
        WHERE last_seen >= NOW() - INTERVAL '48 hours'
        ORDER BY weight DESC
        LIMIT 6
    """
    )

    result = {
        "trending": trending,
        "sentiment": {"positives": positives, "negatives": negatives},
        "relationships": relationships,
        "updated_at": (
            await db.async_execute_one(
                "SELECT MAX(last_seen) as last FROM knowledge_entities"
            )
        )["last"],
    }

    set_cache(cache_key, result, ttl=600)
    return result


@router.get("/intelligence/cluster/{cluster_id}/history")
async def get_cluster_storyline_history(cluster_id: str):
    """Finds related clusters from the past weeks to build a storyline (free, token-less)."""
    validate_cluster_id(cluster_id)

    # Get current cluster's embedding (avg of its articles)
    rows = await db.async_execute(
        "SELECT embedding FROM articles WHERE cluster_id = %s AND embedding IS NOT NULL",
        (cluster_id,),
    )
    if not rows:
        return {"history": []}

    import numpy as np
    import json

    vecs = []
    for r in rows:
        vecs.append(
            json.loads(r["embedding"])
            if isinstance(r["embedding"], str)
            else list(r["embedding"])
        )

    if not vecs:
        return {"history": []}

    avg_vec = np.mean(vecs, axis=0).tolist()
    vec_str = "[" + ",".join(map(str, avg_vec)) + "]"

    # Search for similar clusters from the past 30 days
    # We tighten the similarity threshold to 0.72 and ensure category overlap
    related_clusters = await db.async_execute(
        """
        SELECT a.cluster_id,
               MAX(a.title) as title,
               MIN(a.created_at) as first_seen,
               (1 - (MIN(a.embedding <=> %s::vector))) as similarity,
               MAX(cm.representative_image) as image_url,
               MAX(a.category) as category
        FROM articles a
        LEFT JOIN cluster_metadata cm ON a.cluster_id = cm.cluster_id
        WHERE a.embedding IS NOT NULL
          AND a.cluster_id != %s
          AND a.created_at >= NOW() - INTERVAL '30 days'
        GROUP BY a.cluster_id
        HAVING (1 - (MIN(a.embedding <=> %s::vector))) > 0.72
           AND MAX(a.category) = (SELECT category FROM articles WHERE cluster_id = %s LIMIT 1)
        ORDER BY first_seen DESC
        LIMIT 10
    """,
        (vec_str, cluster_id, vec_str, cluster_id),
    )

    return {"history": related_clusters}


@router.get("/intelligence/cluster/{cluster_id}/research")
@custom_rate_limit("5/minute")
async def get_deep_research(
    request: Request, cluster_id: str, mode: str = "facts", q: str = ""
):
    """
    Performs on-demand cluster research with the best available AI provider.
    """
    validate_cluster_id(cluster_id)
    clean_mode = (mode or "facts").strip().lower()
    if clean_mode not in {"facts", "perspectives", "context", "custom"}:
        clean_mode = "facts"
    clean_query = validate_string_param(
        q, "q", max_length=300, allow_empty=True
    ).strip()
    if clean_mode == "custom" and not clean_query:
        return {
            "status": "error",
            "message": "Vnesete konkretno prasanje za istrazuvanje.",
        }

    query = (
        clean_query if clean_mode == "custom" else _RESEARCH_MODE_QUERIES[clean_mode]
    )
    query_hash = hashlib.sha1(query.encode("utf-8")).hexdigest()[:12]
    cache_key = (
        f"api:intelligence:research:cascade:{cluster_id}:{clean_mode}:{query_hash}:v1"
    )
    cached = cached_response(cache_key)
    if cached:
        return cached

    try:
        context, sources = await _build_gemma_research_context(
            cluster_id, clean_mode, clean_query
        )
        prompt = f"PRASANjE: {query}\n\nKONTEKST ZA ANALIZA:\n{context}"

        # Use cascading AI engine (will route to mistral -> local based on task_type="research")
        raw, provider = sync_call_ai(
            prompt,
            RESEARCH_SYSTEM_PROMPT,
            task_type="research",
            json_mode=True,
            max_tokens=800,
        )

        if not raw:
            return {"status": "error", "message": "Sistemot momentalno ne e dostapen."}

        # Parse structured response
        response = clean_json_response(raw)
        answer = (
            response.get("answer")
            if isinstance(response, dict)
            else str(response or "")
        )
        suggestions = (
            response.get("suggestions", []) if isinstance(response, dict) else []
        )

        # Emergency cleanup: If we still have raw JSON string as answer, strip it
        if isinstance(answer, str) and answer.strip().startswith("{"):
            # If it failed all parsing but is clearly JSON, don't show it to user
            log.warning(
                f"[research] Model returned raw JSON string that failed all cleaning: {answer[:100]}..."
            )
            if '"answer":' in answer:
                # One last attempt to grab the text inside answer key
                m = re.search(r'"answer":\s*"(.*?)"', answer, re.DOTALL)
                if m:
                    answer = m.group(1).replace("\\n", "\n")
            else:
                return {
                    "status": "error",
                    "message": "Sistemot vrati nevaliden format. Obidete se so drugo prasanje.",
                }

        if not answer:
            return {"status": "error", "message": "Ne uspeav da generiram odgovor."}

        result = {
            "status": "success",
            "report": answer,
            "answer": answer,
            "suggestions": suggestions,
            "mode": clean_mode,
            "label": _RESEARCH_MODE_LABELS[clean_mode],
            "provider": provider,
            "sources": sources,
            "timestamp": datetime.datetime.now(),
        }

        set_cache(cache_key, result, ttl=3600)
        return result

    except Exception as e:
        log.error(f"Deep research error: {e}", exc_info=True)
        return {"status": "error", "message": "Greska pri prebaruvanjeto."}


@router.get("/intelligence/cluster/{cluster_id}/analyst")
async def get_cluster_analyst_report(cluster_id: str, mode: str = "facts"):
    """
    Internal 'Deep Intel' Analyst.
    Compatibility wrapper for the Gemma-only research endpoint.
    Modes: 'facts', 'perspectives', 'context'
    """
    validate_cluster_id(cluster_id)
    clean_mode = (mode or "facts").strip().lower()
    if clean_mode not in _RESEARCH_MODE_QUERIES:
        clean_mode = "facts"
    cache_key = f"api:intelligence:analyst:gemma:{cluster_id}:{clean_mode}:v1"
    cached = cached_response(cache_key)
    if cached:
        return cached

    try:
        from local_analyst import analyst

        log.info(
            f"[analyst] Generating Gemma report for {cluster_id} (mode={clean_mode})"
        )
        context, sources = await _build_gemma_research_context(cluster_id, clean_mode)
        response = await asyncio.to_thread(
            analyst.research_query, _RESEARCH_MODE_QUERIES[clean_mode], context
        )
        report = (
            response.get("answer")
            if isinstance(response, dict)
            else str(response or "")
        )

        if not report:
            return {"status": "error", "message": "Analiticarot e zafaten."}

        # Apply final name validation on the report
        from entities import validate_person_names

        report = validate_person_names(report)

        result = {
            "status": "success",
            "report": report,
            "mode": clean_mode,
            "provider": "local_gemma",
            "sources": sources,
        }

        set_cache(cache_key, result, ttl=7200)
        return result

    except Exception as e:
        log.error(f"[analyst] Unexpected error for {cluster_id}: {e}", exc_info=True)
        return {"status": "error", "message": "Greska pri analizata."}


@router.get("/intelligence/source-pulse")
async def get_source_pulse(category: Optional[str] = None):
    from utils import (
        get_source_trust_label,
        get_source_effective_weight,
        cached_response,
        set_cache,
    )

    cat_id = f"cat-{category}" if category else "all"
    cache_key = f"api:intelligence:source-pulse:{cat_id}:v3"
    cached = cached_response(cache_key)
    if cached:
        return cached

    cat_filter = ""
    params = []
    if category:
        cat_filter = "AND a.category = %s"
        params.append(category)

    # Combined query to get current stats, recent headline, and historical baseline
    # Refactored first_report_count to avoid slow correlated subquery
    sql = f"""
        WITH source_stats AS (
            SELECT
                a.source,
                COALESCE(AVG(CAST(s.sentiment->'sentiment'->>'score' AS REAL)), 0) as avg_sentiment,
                COALESCE(AVG(CAST(s.tone_analysis->>'objectivity' AS REAL)), 0) as avg_objectivity,
                COALESCE(AVG(CAST(s.tone_analysis->>'sensationalism' AS REAL)), 0) as avg_sensationalism,
                COUNT(DISTINCT a.cluster_id) as cluster_count
            FROM cluster_summaries s
            JOIN articles a ON s.cluster_id = a.cluster_id
            WHERE s.sentiment IS NOT NULL AND s.created_at >= NOW() - INTERVAL '48 hours'
            {cat_filter}
            GROUP BY a.source
        ),
        historical_baseline AS (
            SELECT
                a.source,
                COALESCE(AVG(CAST(s.sentiment->'tone_analysis'->>'objectivity' AS REAL)), 0) as historical_objectivity
            FROM cluster_summaries s
            JOIN articles a ON s.cluster_id = a.cluster_id
            WHERE s.sentiment IS NOT NULL 
              AND s.created_at >= NOW() - INTERVAL '14 days'
              AND s.created_at < NOW() - INTERVAL '48 hours'
            {cat_filter}
            GROUP BY a.source
        ),
        latest_headlines AS (
            SELECT DISTINCT ON (source) source, title, cluster_id
            FROM articles
            WHERE created_at >= NOW() - INTERVAL '48 hours'
            ORDER BY source, created_at DESC
        ),
        first_reporters_base AS (
            SELECT DISTINCT ON (cluster_id) source, cluster_id
            FROM articles
            WHERE COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '10 days'
            ORDER BY cluster_id, COALESCE(ingested_at, created_at) ASC, created_at ASC
        ),
        first_report_counts AS (
            SELECT fr.source, COUNT(*) as first_report_count
            FROM first_reporters_base fr
            WHERE fr.cluster_id IN (
                SELECT cluster_id FROM articles 
                WHERE COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '7 days' 
                  {cat_filter.replace('a.category', 'category')}
            )
            GROUP BY fr.source
        )
        SELECT
            curr.*,
            lh.title as latest_headline,
            lh.cluster_id as latest_cluster_id,
            COALESCE(hb.historical_objectivity, curr.avg_objectivity) as baseline_objectivity,
            COALESCE(frc.first_report_count, 0) as first_report_count
        FROM source_stats curr
        LEFT JOIN latest_headlines lh ON curr.source = lh.source
        LEFT JOIN historical_baseline hb ON curr.source = hb.source
        LEFT JOIN first_report_counts frc ON curr.source = frc.source
        WHERE curr.cluster_count >= 1
        ORDER BY curr.cluster_count DESC
    """

    # We pass params 3 times because cat_filter is used 3 times in the CTEs
    rows = await db.async_execute(sql, tuple(params * 3))

    for r in rows:
        r["trust_label"] = get_source_trust_label(r["source"])
        r["effective_weight"] = round(get_source_effective_weight(r["source"]), 2)
        # Calculate delta defensively
        if (
            r.get("avg_objectivity") is not None
            and r.get("baseline_objectivity") is not None
        ):
            r["objectivity_delta"] = round(
                r["avg_objectivity"] - r["baseline_objectivity"], 3
            )
        else:
            r["objectivity_delta"] = 0

    result = {"status": "success", "data": rows}
    set_cache(cache_key, result, ttl=600)
    return result


@router.get("/intelligence/entity/{name}")
async def get_entity_profile(name: str):
    # Validate name parameter
    name = validate_string_param(name, "name", max_length=200, allow_empty=False)

    entity = await db.async_execute_one(
        "SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score FROM knowledge_entities WHERE name = %s",
        (name,),
    )
    if not entity:
        entity = await db.async_execute_one(
            "SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score FROM knowledge_entities WHERE LOWER(name) = LOWER(%s) LIMIT 1",
            (name,),
        )
    if entity:
        name = entity["name"]
    else:
        if not await db.async_execute_one(
            f"SELECT 1 FROM cluster_metadata m WHERE {_CASE_INSENSITIVE_TAG_EXISTS} LIMIT 1",
            (name,),
        ):
            raise HTTPException(status_code=404, detail="Subjektot ne e pronajden")
        entity = {
            "name": name,
            "type": "ENTITY",
            "total_mentions": 0,
            "first_seen": None,
            "last_seen": None,
            "sentiment_score": 0,
        }

    relationships = await db.async_execute(
        "SELECT CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity, weight FROM knowledge_relationships WHERE entity_a = %s OR entity_b = %s ORDER BY weight DESC LIMIT 8",
        (name, name, name),
    )
    # Use parameterized queries for array contains
    media_stats = await db.async_execute(
        f"SELECT a.source, COUNT(DISTINCT a.cluster_id) as mention_count FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE {_CASE_INSENSITIVE_TAG_EXISTS} GROUP BY a.source ORDER BY mention_count DESC LIMIT 5",
        (name,),
    )
    category_stats = await db.async_execute(
        f"SELECT a.category, COUNT(DISTINCT a.cluster_id) as count FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE {_CASE_INSENSITIVE_TAG_EXISTS} AND a.category IS NOT NULL AND a.category != '' GROUP BY a.category ORDER BY count DESC LIMIT 5",
        (name,),
    )
    sentiment_history = await db.async_execute(
        f"SELECT DATE(COALESCE(a.ingested_at, a.created_at)) as day, AVG(CAST(s.sentiment->'sentiment'->>'score' AS FLOAT)) as avg_sentiment, COUNT(DISTINCT a.cluster_id) as volume FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id JOIN cluster_summaries s ON a.cluster_id = s.cluster_id WHERE {_CASE_INSENSITIVE_TAG_EXISTS} AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '14 days' AND s.sentiment IS NOT NULL GROUP BY day ORDER BY day ASC",
        (name,),
    )
    recent = await db.async_execute(
        "SELECT c.cluster_id, (SELECT title FROM articles WHERE cluster_id = c.cluster_id ORDER BY COALESCE(ingested_at, created_at) DESC LIMIT 1) as title, c.updated_at as created_at, s.summary, s.sentiment FROM cluster_metadata c LEFT JOIN cluster_summaries s ON c.cluster_id = s.cluster_id WHERE EXISTS (SELECT 1 FROM unnest(COALESCE(c.tags, '{}')) AS tag WHERE LOWER(tag) = LOWER(%s)) ORDER BY c.updated_at DESC LIMIT 10",
        (name,),
    )

    processed = []
    for c in recent:
        bullets = [
            re.sub(r"^[-•*]\s*", "", line).strip()
            for line in (c["summary"] or "").split("\n")
            if line.strip() and not line.strip().lower().startswith("clanci:")
        ]
        sent = None
        try:
            sent = (
                json.loads(c["sentiment"])
                if isinstance(c["sentiment"], str)
                else c["sentiment"]
            )
        except Exception:
            sent = {"sentiment": {"score": 0, "tone": "neutralno"}}
        processed.append(
            {
                "cluster_id": c["cluster_id"],
                "title": cleanAndDecode(c["title"]),
                "created_at": c["created_at"],
                "bullets": bullets[:2],
                "sentiment": sent,
            }
        )

    return {
        "profile": entity,
        "related": relationships,
        "media": media_stats,
        "categories": category_stats,
        "sentiment_history": sentiment_history,
        "clusters": processed,
    }


@router.get("/intelligence/global-pulse", response_model=GlobalPulseResponse)
async def get_global_pulse(category: Optional[str] = None):
    """Public high-level intelligence stats for the Pulse page."""
    cat_id = f"cat-{category}" if category else "all"
    cache_key = f"api:intelligence:global-pulse:{cat_id}:v4"
    cached = cached_response(cache_key)
    if cached:
        return cached

    cat_filter = ""
    params = []
    if category:
        cat_filter = "AND a.category = %s"
        params.append(category)

    # Run DB queries in parallel
    async def get_velocity():
        return await db.async_execute(
            f"""
            SELECT date_trunc('hour', COALESCE(a.ingested_at, a.created_at)) AS t, COUNT(*) AS n 
            FROM articles a
            WHERE COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '24 hours' {cat_filter}
            GROUP BY t ORDER BY t
        """,
            tuple(params),
        )

    async def get_last_24h_count():
        count_filter = ""
        count_params = []
        if category:
            count_filter = "AND category = %s"
            count_params.append(category)
        return await db.async_execute_one(
            f"""
            SELECT COUNT(*) FROM articles
            WHERE COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '24 hours' {count_filter}
        """,
            tuple(count_params),
        )

    async def get_by_category():
        # Only needed if not filtering by category
        if category:
            return []
        return await db.async_execute(
            """
            SELECT a.category, COUNT(*) AS n 
            FROM articles a
            WHERE COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '24 hours'
              AND a.category IS NOT NULL
              AND a.category != ''
            GROUP BY a.category ORDER BY n DESC
        """
        )

    async def get_topic_sentiment():
        return await db.async_execute(
            f"""
            SELECT 
                t as topic,
                COALESCE(AVG(CAST(s.sentiment->'sentiment'->>'score' AS REAL)), 0) as avg_sentiment,
                COALESCE(AVG(CAST(s.tone_analysis->>'objectivity' AS REAL)), 0) as avg_objectivity,
                COALESCE(AVG(CAST(s.tone_analysis->>'sensationalism' AS REAL)), 0) as avg_sensationalism,
                COUNT(*) as n
            FROM cluster_summaries s
            JOIN cluster_metadata m ON s.cluster_id = m.cluster_id,
            UNNEST(m.topics) t
            WHERE s.sentiment IS NOT NULL AND s.created_at >= NOW() - INTERVAL '24 hours'
              AND m.topics IS NOT NULL AND array_length(m.topics, 1) > 0
              {cat_filter.replace('a.category', 'm.category')}
            GROUP BY t ORDER BY n DESC
        """,
            tuple(params),
        )

    velocity, by_category, by_topic_sentiment, count_row = await asyncio.gather(
        get_velocity(), get_by_category(), get_topic_sentiment(), get_last_24h_count()
    )

    velocity_total = sum(row["n"] for row in velocity)
    last_24h = int((count_row or {}).get("count") or velocity_total)

    # 3. Pluralism & AI Metrics (Aggregated)
    from .common import build_intelligence_summary_payload

    intel = await build_intelligence_summary_payload(last_24h, category=category)

    # 4. Top Trending Entities (with 48h fallback)
    async def fetch_top_entities(interval_str):
        if category:
            sql = f"""
                SELECT t.name, COUNT(DISTINCT t.cluster_id) as total_mentions, ke.sentiment_score, ke.type
                FROM (
                    SELECT UNNEST(cm.tags) as name, cm.cluster_id
                    FROM cluster_metadata cm
                    JOIN articles a ON cm.cluster_id = a.cluster_id
                    WHERE a.category = %s AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL {interval_str}
                ) t
                LEFT JOIN knowledge_entities ke ON t.name = ke.name
                WHERE t.name IS NOT NULL AND length(t.name) >= 3
                GROUP BY t.name, ke.sentiment_score, ke.type
                ORDER BY total_mentions DESC
                LIMIT 12
            """
            rows = await db.async_execute(sql, (category,))
        else:
            sql = f"""
                SELECT t.name, COUNT(DISTINCT t.cluster_id) as total_mentions, ke.sentiment_score, ke.type
                FROM (
                    SELECT UNNEST(cm.tags) as name, cm.cluster_id
                    FROM cluster_metadata cm
                    JOIN articles a ON cm.cluster_id = a.cluster_id
                    WHERE COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL {interval_str}
                ) t
                LEFT JOIN knowledge_entities ke ON t.name = ke.name
                WHERE t.name IS NOT NULL AND length(t.name) >= 3
                GROUP BY t.name, ke.sentiment_score, ke.type
                ORDER BY total_mentions DESC
                LIMIT 12
            """
            rows = await db.async_execute(sql)
            
        # Post-process: clean names and filter out common generic tags
        from .common import _is_valid_focus_entity
        from nlp import normalize_tag_name
        
        processed = []
        seen = set()
        for r in rows:
            name = normalize_tag_name(r["name"])
            if not _is_valid_focus_entity(name, None):
                continue
            if name.casefold() in seen:
                continue
            seen.add(name.casefold())
            processed.append({
                "name": name,
                "total_mentions": r["total_mentions"],
                "sentiment_score": r["sentiment_score"] or 0,
                "type": r["type"] or "ENTITY"
            })
            if len(processed) >= 8:
                break
        return processed

    top_entities = await fetch_top_entities("'24 hours'")
    if not top_entities or len(top_entities) < 3:
        top_entities = await fetch_top_entities("'48 hours'")

    res = {
        "status": "success",
        "timestamp": datetime.datetime.now(),
        "last_24h": last_24h,
        "velocity": velocity,
        "by_category": by_category,
        "by_topic_sentiment": by_topic_sentiment,
        "intelligence": intel,
        "top_entities": top_entities,
    }
    set_cache(cache_key, res, ttl=600)
    return res


@router.get("/entity-graph/{entity_name}")
@custom_rate_limit("30/minute")
async def entity_graph_lookup(request: Request, entity_name: str):
    """Fetches persistent knowledge about an entity from the local graph."""
    row = await db.async_execute_one(
        """
        SELECT bio_summary, importance_score, last_seen, category 
        FROM entity_knowledge WHERE entity_name = %s
    """,
        (entity_name,),
    )
    if not row:
        row = await db.async_execute_one(
            """
            SELECT
                COALESCE(metadata->>'bio_summary', '') AS bio_summary,
                total_mentions AS importance_score,
                last_seen,
                COALESCE(type, 'ENTITY') AS category
            FROM knowledge_entities
            WHERE name = %s
        """,
            (entity_name,),
        )

    if not row:
        return {"status": "not_found"}

    return {"status": "success", "data": row}


@router.get("/research/{cluster_id}")
@custom_rate_limit("10/minute")
async def cluster_research(request: Request, cluster_id: str, q: str):
    """Researches a cluster based on a user query using Gemma 2."""
    from local_analyst import analyst

    # Get cluster context
    row = await db.async_execute_one(
        """
        SELECT summary, generated_article 
        FROM cluster_summaries WHERE cluster_id = %s
    """,
        (cluster_id,),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Klasterot ne e pronajden")

    context = f"{row['summary']}\n{row['generated_article']}"
    res = analyst.research_query(q, context)

    return {
        "status": "success",
        "answer": res.get("answer"),
        "suggestions": res.get("suggestions", []),
    }


@router.get("/intelligence/top-entities")
async def get_top_entities(limit: int = 10):
    cache_key = f"api:top-entities:{limit}"
    cached = cached_response(cache_key)
    if cached:
        return cached
    fetch_limit = max(limit * 6, 40)
    rows = await db.async_execute(
        f"SELECT tag AS name, COUNT(*) AS total_mentions FROM (SELECT cm.cluster_id, UNNEST(cm.tags) AS tag FROM cluster_metadata cm JOIN articles a ON a.cluster_id = cm.cluster_id WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '48 hours' AND cm.tags IS NOT NULL GROUP BY cm.cluster_id, tag) t GROUP BY tag ORDER BY total_mentions DESC LIMIT %s",
        (fetch_limit,),
    )
    aggregated = {}
    for row in rows:
        norm = normalize_person_surface_name(
            normalize_tag_name(normalize_entity_name(row["name"]))
        )
        if not _is_valid_focus_entity(norm, None):
            continue
        key = norm.casefold()
        aggregated[key] = {
            "name": norm,
            "type": None,
            "total_mentions": int(aggregated.get(key, {}).get("total_mentions", 0))
            + int(row.get("total_mentions") or 0),
        }
    filtered = _compact_focus_entities(list(aggregated.values()), limit=limit)
    set_cache(cache_key, filtered, ttl=600)
    return filtered


@router.get("/intelligence/entity/{name}/topics")
async def get_entity_topics(name: str):
    # Validate name parameter
    name = validate_string_param(name, "name", max_length=200, allow_empty=False)
    return {
        "status": "success",
        "data": await db.async_execute(
            "SELECT a.topic, COUNT(*) as count FROM articles a JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id WHERE ce.entity_name = %s AND a.topic IS NOT NULL GROUP BY a.topic ORDER BY count DESC LIMIT 5",
            (name,),
        ),
    }


@router.get("/intelligence/live-map")
async def get_live_map():
    return {
        "status": "success",
        "data": await db.async_execute(
            f"SELECT a.source, COUNT(*) as activity_score FROM articles a WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' GROUP BY a.source ORDER BY activity_score DESC"
        ),
    }


@router.get("/intelligence/compare-sources")
async def compare_sources(s1: str, s2: str):
    # Validate source names
    s1 = validate_string_param(s1, "s1", max_length=100, allow_empty=False)
    s2 = validate_string_param(s2, "s2", max_length=100, allow_empty=False)

    rows = await db.async_execute(
        "SELECT a.source, AVG(CAST(s.sentiment->'sentiment'->>'score' AS REAL)) as avg_sentiment, AVG(CAST(s.sentiment->'tone_analysis'->>'objectivity' AS REAL)) as avg_objectivity, AVG(CAST(s.sentiment->'tone_analysis'->>'sensationalism' AS REAL)) as avg_sensationalism, COUNT(DISTINCT a.cluster_id) as cluster_count FROM cluster_summaries s JOIN articles a ON s.cluster_id = a.cluster_id WHERE a.source = ANY(%s) AND s.sentiment IS NOT NULL AND s.created_at >= NOW() - INTERVAL '30 days' GROUP BY a.source",
        ([s1, s2],),
    )
    overlap = await db.async_execute_one(
        "WITH src_c AS (SELECT source, cluster_id FROM articles WHERE source = ANY(%s) AND created_at >= NOW() - INTERVAL '30 days' GROUP BY source, cluster_id) SELECT COUNT(*) FILTER (WHERE s1.cluster_id IS NOT NULL AND s2.cluster_id IS NOT NULL) as shared_clusters, COUNT(*) FILTER (WHERE s1.cluster_id IS NOT NULL AND s2.cluster_id IS NULL) as s1_exclusive, COUNT(*) FILTER (WHERE s1.cluster_id IS NULL AND s2.cluster_id IS NOT NULL) as s2_exclusive FROM (SELECT DISTINCT cluster_id FROM src_c WHERE source = %s) s1 FULL OUTER JOIN (SELECT DISTINCT cluster_id FROM src_c WHERE source = %s) s2 ON s1.cluster_id = s2.cluster_id",
        ([s1, s2], s1, s2),
    )
    return {"status": "success", "data": rows, "overlap": overlap}


@router.post("/intelligence/recommendations")
async def get_personalized_recommendations(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Nevaliden JSON")
    recent_ids = validate_list_param(
        payload.get("recentlyRead", []),
        "recentlyRead",
        max_items=10,
        max_item_length=64,
    )
    followed = validate_list_param(
        payload.get("followedTopics", []),
        "followedTopics",
        max_items=10,
        max_item_length=100,
    )
    interest_vector = payload.get("interestVector")
    limit = min(max(1, int(payload.get("limit", 6))), 20)
    if not recent_ids and not followed and not interest_vector:
        return {"status": "success", "clusters": []}
    user_vectors = []

    if (
        interest_vector
        and isinstance(interest_vector, list)
        and len(interest_vector) == 384
    ):
        user_vectors.append(interest_vector)

    if recent_ids:
        rows = await db.async_execute(
            "SELECT embedding FROM articles WHERE cluster_id = ANY(%s) AND embedding IS NOT NULL LIMIT 20",
            (recent_ids,),
        )
        for r in rows:
            if r["embedding"]:
                user_vectors.append(
                    json.loads(r["embedding"])
                    if isinstance(r["embedding"], str)
                    else list(r["embedding"])
                )
    for t in followed:
        vec = generate_query_embedding(t)
        if vec:
            user_vectors.append(vec)
    if not user_vectors:
        return {"status": "success", "clusters": []}
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
            if len(cids) >= limit:
                break
    if not cids:
        return {"status": "success", "clusters": []}
    rows = await db.async_execute(
        "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
        (cids,),
    )
    cmap = {}
    for r in rows:
        cmap.setdefault(r["cluster_id"], []).append(r)
    formatted = []
    for cid in cids:
        arts = cmap.get(cid, [])
        if not arts:
            continue
        s_row = await db.async_execute_one(
            "SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cid,)
        )
        m_row = await db.async_execute_one(
            "SELECT representative_image FROM cluster_metadata WHERE cluster_id = %s",
            (cid,),
        )
        formatted.append(
            {
                "cluster_id": cid,
                "articles": arts,
                "representative_image": (
                    m_row["representative_image"] if m_row else None
                ),
                "score": score_cluster(arts),
                "has_synthesis": bool(s_row and s_row["summary"]),
                "is_breaking": any(a.get("is_breaking") for a in arts),
                "reason": "Predlog za Vas",
            }
        )
    return {"status": "success", "clusters": formatted}


@router.get("/intelligence/briefing")
async def get_latest_briefing(date: Optional[str] = None):
    """Fetch the latest or specific AI-generated daily briefing."""
    if date:
        from .security import validate_date

        validate_date(date)
        row = await db.async_execute_one(
            "SELECT * FROM daily_briefings WHERE date = %s", (date,)
        )
    else:
        row = await db.async_execute_one(
            "SELECT * FROM daily_briefings ORDER BY date DESC LIMIT 1"
        )

    if not row:
        return {"status": "error", "message": "Brifingot ne e pronajden"}

    target_date = row["date"]

    # 1. Fetch metadata for the sidebar
    subjects = await db.async_execute(
        """
        SELECT name, total_mentions 
        FROM knowledge_entities 
        WHERE type = 'PERSON' AND last_seen >= %s::date - INTERVAL '24 hours' 
          AND last_seen <= %s::date + INTERVAL '23 hours 59 minutes'
        ORDER BY total_mentions DESC LIMIT 6
    """,
        (target_date, target_date),
    )

    locations = await db.async_execute(
        """
        SELECT name, total_mentions 
        FROM knowledge_entities 
        WHERE type = 'GPE' AND last_seen >= %s::date - INTERVAL '24 hours'
          AND last_seen <= %s::date + INTERVAL '23 hours 59 minutes'
        ORDER BY total_mentions DESC LIMIT 8
    """,
        (target_date, target_date),
    )

    # 2. Historical dates for navigation
    historical = await db.async_execute(
        "SELECT date::text as day FROM daily_briefings ORDER BY date DESC LIMIT 14"
    )

    # 3. Lead cluster for the day
    lead_cluster = await db.async_execute_one(
        """
        SELECT s.cluster_id, s.synthetic_headline, m.representative_image
        FROM cluster_summaries s
        JOIN cluster_metadata m ON s.cluster_id = m.cluster_id
        JOIN articles a ON s.cluster_id = a.cluster_id
        WHERE a.created_at >= %s::date AND a.created_at < %s::date + INTERVAL '1 day'
        GROUP BY s.cluster_id, s.synthetic_headline, m.representative_image, s.pluralism_score
        ORDER BY s.pluralism_score DESC, COUNT(a.id) DESC
        LIMIT 1
    """,
        (target_date, target_date),
    )

    # Fetch stats for that day
    stats_res = await db.async_execute_one(
        """
        SELECT 
            COUNT(*) as total_articles,
            COUNT(DISTINCT source) as total_sources
        FROM articles 
        WHERE created_at >= %s::date AND created_at < %s::date + INTERVAL '1 day'
    """,
        (target_date, target_date),
    )

    return {
        "status": "success",
        "date": target_date,
        "content": row["content"],
        "subjects": subjects,
        "locations": locations,
        "historical_dates": historical,
        "lead_cluster": lead_cluster,
        "day_stats": stats_res,
    }
