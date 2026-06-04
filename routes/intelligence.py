import asyncio
import datetime
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from core.database import db_manager as db
from core.embeddings import generate_query_embedding
from core.entities import normalize_entity_name, normalize_person_surface_name
from core.language import transliterate_lat_to_cyr
from core.limiter import custom_rate_limit
from nlp import normalize_tag_name
from utils import cached_response, score_cluster, set_cache

from .common import _is_valid_focus_entity, cleanAndDecode
from .security import validate_cluster_id, validate_list_param, validate_string_param

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
    ingestion_rate: float = 0.0  # items per minute
    velocity: List[PulseVelocity]
    by_category: List[PulseCategory]
    by_topic_sentiment: List[Dict[str, Any]] = []
    intelligence: Dict[str, Any]
    top_entities: List[Dict[str, Any]] = []


_FRESHNESS_EXPR = "COALESCE(ingested_at, created_at)"
_CASE_INSENSITIVE_TAG_EXISTS = (
    "EXISTS (SELECT 1 FROM unnest(COALESCE(m.tags, '{}')) AS tag WHERE LOWER(tag) = LOWER(%s))"
)

_RESEARCH_MODE_QUERIES = {
    "sr": {
        "facts": (
            "Izvuci najvažnije brojke, datume, činjenice i vremenski okvir iz ove priče. "
            "Ne dodaj brojke koje ne postoje u kontekstu."
        ),
        "perspectives": (
            "Identifikuj ključne aktere, njihove stavove, izjave i različite uglove u priči. "
            "Ne izmišljaj izjave koje nisu u kontekstu."
        ),
        "context": (
            "Objasni širi kontekst, prethodna povezana dešavanja i moguće posledice ove priče. "
            "Jasno odvoji ono što je u izvorima od analitičkog okvira."
        ),
    },
    "mk": {
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
        raise HTTPException(status_code=404, detail="klaster nije pronadjen")

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
                parts.append(f"PROVERKA NA FAKTI (Sistemska analiza):\n{json.dumps(vr, ensure_ascii=False, indent=2)}")
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
        parts.append(f"--- izvor: {source} ({article['created_at'].strftime('%H:%M %d.%m.%Y')}) ---\n{text}")

    if mode == "context":
        try:
            import numpy as np

            vecs = [
                (json.loads(a["embedding"]) if isinstance(a.get("embedding"), str) else list(a["embedding"]))
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
                        [f"- {p['title']} ({p['created_at'].strftime('%d.%m.%Y')})" for p in past_events]
                    )
                    parts.append(f"POVRZANI PRETHODNI NASTANI OD BAZATA:\n{history_list}")
        except Exception as e:
            log.warning(f"Failed to fetch Gemma research history context: {e}")

    return "\n\n".join(parts)[:45000], sources


def _compact_focus_entities(items: list[dict], limit: int) -> list[dict]:
    by_key = {
        str(item.get("name") or "").casefold(): dict(item) for item in items if str(item.get("name") or "").strip()
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
        "updated_at": (await db.async_execute_one("SELECT MAX(last_seen) as last FROM knowledge_entities"))["last"],
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

    import json

    import numpy as np

    vecs = []
    for r in rows:
        vecs.append(json.loads(r["embedding"]) if isinstance(r["embedding"], str) else list(r["embedding"]))

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
        HAVING (1 - (MIN(a.embedding <=> %s::vector))) > 0.65
        ORDER BY first_seen DESC
        LIMIT 10
    """,
        (vec_str, cluster_id, vec_str),
    )

    return {"history": related_clusters}


@router.get("/intelligence/cluster/{cluster_id}/research")
@custom_rate_limit("5/minute")
async def get_deep_research(request: Request, cluster_id: str, mode: str = "facts", q: str = "", lang: str = "sr"):
    """
    Performs on-demand cluster research with the best available AI provider.
    """
    validate_cluster_id(cluster_id)
    clean_mode = (mode or "facts").strip().lower()
    clean_query = validate_string_param(q, "q", max_length=1000, allow_empty=True).strip()
    if clean_mode not in {"facts", "perspectives", "context", "custom"}:
        return {
            "status": "error",
            "message": (
                "Nevaliden tip na istrazuvanje."
                if lang == "mk"
                else "Nevalidan tip istraživanja."
            ),
        }
    
    if clean_mode == "custom" and not clean_query:
        return {
            "status": "error",
            "message": (
                "Vnesete konkretno prasanje za istrazuvanje."
                if lang == "mk"
                else "Unesite konkretno pitanje za istraživanje."
            ),
        }

    # Caching check
    effective_lang = lang if lang in _RESEARCH_MODE_QUERIES else "sr"
    query = clean_query if clean_mode == "custom" else _RESEARCH_MODE_QUERIES[effective_lang][clean_mode]
    query_hash = hashlib.sha1(query.encode("utf-8")).hexdigest()[:12]
    cache_key = f"api:intelligence:research:cascade:{cluster_id}:{clean_mode}:{query_hash}:{lang}:v3"
    cached = cached_response(cache_key)
    if cached:
        return cached

    # Delegate to service
    from core.services.research_service import ResearchService
    response = await ResearchService.get_cluster_research(cluster_id, clean_mode, clean_query, lang)

    if not response:
        return {
            "status": "error",
            "message": (
                "Sistemot e preoptereten, obidete se povtorno za nekolku minuti."
                if lang == "mk"
                else "Sistem je trenutno preopterećen, pokušajte ponovo za nekoliko minuta."
            ),
        }

    # Normalize response: clean_json_response may return a plain string
    if isinstance(response, str):
        response = {"answer": response, "suggestions": []}

    # Final result structure
    result = {
        "status": "success",
        "report": response.get("answer"),
        "answer": response.get("answer"),
        "suggestions": response.get("suggestions", []),
        "mode": clean_mode,
        "label": _RESEARCH_MODE_LABELS[clean_mode],
        "provider": response.get("provider"),
        "sources": response.get("sources", []),
        "search_queries": response.get("search_queries", []),
    }
    # ... (store in cache) ...
    try:
        set_cache(cache_key, result, ttl=3600)
        return result
    except Exception as e:
        log.error(f"Deep research error: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "Greška pri pretraživanju."
        }




@router.get("/intelligence/cluster/{cluster_id}/analyst")
async def get_cluster_analyst_report(cluster_id: str, mode: str = "facts", lang: str = "sr"):
    """
    Internal 'Deep Intel' Analyst.
    Refactored to use ResearchService for unified research logic.
    """
    validate_cluster_id(cluster_id)
    clean_mode = (mode or "facts").strip().lower()
    
    from core.services.research_service import ResearchService
    response = await ResearchService.get_cluster_research(cluster_id, clean_mode, "", lang)
    
    if not response:
        return {"status": "error", "message": "Greška pri generisanju izveštaja."}

    if isinstance(response, str):
        response = {"answer": response, "suggestions": []}

    return {
        "status": "success",
        "report": response.get("answer"),
        "answer": response.get("answer"),
        "suggestions": response.get("suggestions", []),
    }


@router.get("/intelligence/source-pulse")
async def get_source_pulse(category: Optional[str] = None, lang: Optional[str] = "sr"):
    from utils import cached_response, get_source_effective_weight, get_source_trust_label, set_cache

    cat_id = f"cat-{category}-{lang}" if category else f"all-{lang}"
    cache_key = f"api:intelligence:source-pulse:{cat_id}:v4"
    cached = cached_response(cache_key)
    if cached:
        return cached

    cat_filter = ""
    country_filter = "MK" if lang == "mk" else "RS"
    params = [lang, country_filter]
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
            WHERE s.lang = %s AND a.country = %s AND s.sentiment IS NOT NULL AND s.created_at >= NOW() - INTERVAL '48 hours'
            {cat_filter}
            GROUP BY a.source
        ),
        historical_baseline AS (
            SELECT
                a.source,
                COALESCE(AVG(CAST(s.sentiment->'tone_analysis'->>'objectivity' AS REAL)), 0) as historical_objectivity
            FROM cluster_summaries s
            JOIN articles a ON s.cluster_id = a.cluster_id
            WHERE s.lang = %s AND a.country = %s AND s.sentiment IS NOT NULL
              AND s.created_at >= NOW() - INTERVAL '14 days'
              AND s.created_at < NOW() - INTERVAL '48 hours'
            {cat_filter}
            GROUP BY a.source
        ),
        latest_headlines AS (
            SELECT DISTINCT ON (source) source, title, cluster_id
            FROM articles
            WHERE country = %s AND created_at >= NOW() - INTERVAL '48 hours'
            ORDER BY source, created_at DESC
        ),
        first_reporters_base AS (
            SELECT DISTINCT ON (cluster_id) source, cluster_id
            FROM articles
            WHERE country = %s AND COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '10 days'
            ORDER BY cluster_id, COALESCE(ingested_at, created_at) ASC, created_at ASC
        ),
        first_report_counts AS (
            SELECT fr.source, COUNT(*) as first_report_count
            FROM first_reporters_base fr
            WHERE fr.cluster_id IN (
                SELECT cluster_id FROM articles
                WHERE country = %s AND COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '7 days'
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

    # We need to construct the params tuple based on the CTEs usage
    # source_stats: lang, country, [category]
    # historical_baseline: lang, country, [category]
    # latest_headlines: country
    # first_reporters_base: country
    # first_report_counts: country, [category]

    final_params = []
    # source_stats
    final_params.extend([lang, country_filter])
    if category:
        final_params.append(category)
    # historical_baseline
    final_params.extend([lang, country_filter])
    if category:
        final_params.append(category)
    # latest_headlines
    final_params.append(country_filter)
    # first_reporters_base
    final_params.append(country_filter)
    # first_report_counts
    final_params.append(country_filter)
    if category:
        final_params.append(category)

    rows = await db.async_execute(sql, tuple(final_params))

    for r in rows:
        r["trust_label"] = get_source_trust_label(r["source"], lang=lang)
        r["effective_weight"] = round(get_source_effective_weight(r["source"]), 2)
        # Calculate delta defensively
        if r.get("avg_objectivity") is not None and r.get("baseline_objectivity") is not None:
            r["objectivity_delta"] = round(r["avg_objectivity"] - r["baseline_objectivity"], 3)
        else:
            r["objectivity_delta"] = 0

    result = {"status": "success", "data": rows}
    set_cache(cache_key, result, ttl=600)
    return result


@router.get("/intelligence/entity/{name}")
async def get_entity_profile(name: str, lang: Optional[str] = "sr"):
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
            raise HTTPException(status_code=404, detail="Subjekat nije pronadjen")
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
        f"SELECT DATE(COALESCE(a.ingested_at, a.created_at)) as day, AVG(CAST(s.sentiment->'sentiment'->>'score' AS FLOAT)) as avg_sentiment, COUNT(DISTINCT a.cluster_id) as volume FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id JOIN cluster_summaries s ON a.cluster_id = s.cluster_id WHERE {_CASE_INSENSITIVE_TAG_EXISTS} AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '14 days' AND s.sentiment IS NOT NULL AND s.lang = %s GROUP BY day ORDER BY day ASC",
        (name, lang),
    )
    recent = await db.async_execute(
        "SELECT c.cluster_id, (SELECT title FROM articles WHERE cluster_id = c.cluster_id ORDER BY COALESCE(ingested_at, created_at) DESC LIMIT 1) as title, c.updated_at as created_at, s.summary, s.sentiment FROM cluster_metadata c LEFT JOIN cluster_summaries s ON c.cluster_id = s.cluster_id AND s.lang = %s WHERE EXISTS (SELECT 1 FROM unnest(COALESCE(c.tags, '{}')) AS tag WHERE LOWER(tag) = LOWER(%s)) ORDER BY c.updated_at DESC LIMIT 10",
        (lang, name),
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
            sent = json.loads(c["sentiment"]) if isinstance(c["sentiment"], str) else c["sentiment"]
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
async def get_global_pulse(category: Optional[str] = None, lang: Optional[str] = "sr"):
    """Public high-level intelligence stats for the Pulse page."""
    cat_id = f"cat-{category}-{lang}" if category else f"all-{lang}"
    cache_key = f"api:intelligence:global-pulse:{cat_id}:v5"
    cached = cached_response(cache_key)
    if cached:
        return cached

    cat_filter = ""
    country_filter = "MK" if lang == "mk" else "RS"
    params = [country_filter]
    if category:
        cat_filter = "AND a.category = %s"
        params.append(category)

    # Run DB queries in parallel
    async def get_velocity():
        return await db.async_execute(
            f"""
            SELECT date_trunc('hour', COALESCE(a.ingested_at, a.created_at)) AS t, COUNT(*) AS n
            FROM articles a
            WHERE a.country = %s AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '24 hours' {cat_filter}
            GROUP BY t ORDER BY t
        """,
            tuple(params),
        )

    async def get_last_24h_count():
        count_filter = ""
        count_params = [country_filter]
        if category:
            count_filter = "AND category = %s"
            count_params.append(category)
        return await db.async_execute_one(
            f"""
            SELECT COUNT(*) FROM articles
            WHERE country = %s AND COALESCE(ingested_at, created_at) >= NOW() - INTERVAL '24 hours' {count_filter}
        """,
            tuple(count_params),
        )

    async def get_ingestion_rate():
        # Last 3 hours ingestion rate
        rate_params = [country_filter]
        if category:
            rate_params.append(category)

        row = await db.async_execute_one(
            f"""
            SELECT COUNT(*) as n
            FROM articles a
            WHERE a.country = %s AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '3 hours' {cat_filter}
        """,
            tuple(rate_params),
        )
        count = (row or {}).get("n", 0)
        return round(float(count) / 180.0, 2)  # items per minute

    async def get_by_category():
        # Only needed if not filtering by category
        if category:
            return []
        return await db.async_execute(
            """
            SELECT a.category, COUNT(*) AS n
            FROM articles a
            WHERE a.country = %s AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '24 hours'
              AND a.category IS NOT NULL
              AND a.category != ''
            GROUP BY a.category ORDER BY n DESC
            """,
            (country_filter,),
        )

    async def get_topic_sentiment():
        ts_params = [lang, country_filter]
        if category:
            ts_params.append(category)
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
              AND s.lang = %s AND m.category IN (SELECT category FROM articles WHERE country = %s)
              {cat_filter.replace('a.category', 'm.category')}
            GROUP BY t ORDER BY n DESC
        """,
            tuple(ts_params),
        )

    velocity, by_category, by_topic_sentiment, count_row, ingestion_rate = await asyncio.gather(
        get_velocity(), get_by_category(), get_topic_sentiment(), get_last_24h_count(), get_ingestion_rate()
    )

    velocity_total = sum(row["n"] for row in velocity)
    last_24h = int((count_row or {}).get("count") or velocity_total)

    # 3. Pluralism & AI Metrics (Aggregated)
    from .common import build_intelligence_summary_payload

    intel = await build_intelligence_summary_payload(last_24h, category=category, lang=lang)

    # 4. Top Trending Entities (with 48h fallback)
    async def fetch_top_entities(interval_str):
        if category:
            sql = f"""
                SELECT t.name, COUNT(DISTINCT t.cluster_id) as total_mentions, ke.sentiment_score, ke.type
                FROM (
                    SELECT UNNEST(cm.tags) as name, cm.cluster_id
                    FROM cluster_metadata cm
                    JOIN articles a ON cm.cluster_id = a.cluster_id
                    WHERE a.country = %s AND a.category = %s AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL {interval_str}
                ) t
                LEFT JOIN knowledge_entities ke ON t.name = ke.name
                WHERE t.name IS NOT NULL AND length(t.name) >= 3
                GROUP BY t.name, ke.sentiment_score, ke.type
                ORDER BY total_mentions DESC
                LIMIT 12
            """
            rows = await db.async_execute(
                sql,
                (
                    country_filter,
                    category,
                ),
            )
        else:
            sql = f"""
                SELECT t.name, COUNT(DISTINCT t.cluster_id) as total_mentions, ke.sentiment_score, ke.type
                FROM (
                    SELECT UNNEST(cm.tags) as name, cm.cluster_id
                    FROM cluster_metadata cm
                    JOIN articles a ON cm.cluster_id = a.cluster_id
                    WHERE a.country = %s AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL {interval_str}
                ) t
                LEFT JOIN knowledge_entities ke ON t.name = ke.name
                WHERE t.name IS NOT NULL AND length(t.name) >= 3
                GROUP BY t.name, ke.sentiment_score, ke.type
                ORDER BY total_mentions DESC
                LIMIT 12
            """
            rows = await db.async_execute(sql, (country_filter,))

        # Post-process: clean names and filter out common generic tags
        from nlp import normalize_tag_name

        from .common import _is_valid_focus_entity

        processed = []
        seen = set()
        for r in rows:
            name = normalize_tag_name(r["name"])
            if not _is_valid_focus_entity(name, None):
                continue
            
            if lang == "mk":
                name = transliterate_lat_to_cyr(name)
                
            if name.casefold() in seen:
                continue
            seen.add(name.casefold())
            processed.append(
                {
                    "name": name,
                    "total_mentions": r["total_mentions"],
                    "sentiment_score": r["sentiment_score"] or 0,
                    "type": r["type"] or "ENTITY",
                }
            )
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
        "ingestion_rate": ingestion_rate,
        "velocity": velocity,
        "by_category": by_category,
        "by_topic_sentiment": by_topic_sentiment,
        "intelligence": intel,
        "top_entities": top_entities,
    }
    set_cache(cache_key, res, ttl=600)
    return res


@router.get("/intelligence/network-graph")
@custom_rate_limit("30/minute")
async def get_network_graph(
    request: Request,
    entity: Optional[str] = None,
    limit: int = 50,
    min_weight: int = 2
):
    """Fetches the nodes and edges for the interactive media network graph visualization."""
    limit = min(100, max(10, limit))
    min_weight = max(1, min_weight)
    
    # Cache key based on params
    cache_key = f"presek:network_graph:entity:{entity or 'global'}:limit:{limit}:min:{min_weight}"
    cached = cached_response(cache_key)
    if cached:
        return cached

    nodes = []
    edges = []
    seen_entities = set()

    if entity:
        # Star-shaped sub-network around the centered entity
        entity_name_cleaned = entity.strip()
        
        # Get matching relationships involving the target entity
        relationships = await db.async_execute(
            """
            SELECT entity_a, entity_b, weight, count_a_to_b, count_b_to_a
            FROM knowledge_relationships
            WHERE (entity_a = %s OR entity_b = %s) AND weight >= %s
            ORDER BY weight DESC
            LIMIT %s
            """,
            (entity_name_cleaned, entity_name_cleaned, min_weight, limit),
        )
    else:
        # Global top relationships view
        relationships = await db.async_execute(
            """
            SELECT entity_a, entity_b, weight, count_a_to_b, count_b_to_a
            FROM knowledge_relationships
            WHERE weight >= %s
            ORDER BY weight DESC
            LIMIT %s
            """,
            (min_weight, limit),
        )

    # Gather unique entities
    for rel in relationships:
        seen_entities.add(rel["entity_a"])
        seen_entities.add(rel["entity_b"])
        
        c_a_to_b = rel.get("count_a_to_b") or 0
        c_b_to_a = rel.get("count_b_to_a") or 0
        
        # Determine dominant direction
        if c_b_to_a > c_a_to_b:
            edge_src = rel["entity_b"]
            edge_tgt = rel["entity_a"]
            direction = "b_to_a"
        elif c_a_to_b > c_b_to_a:
            edge_src = rel["entity_a"]
            edge_tgt = rel["entity_b"]
            direction = "a_to_b"
        else:
            edge_src = rel["entity_a"]
            edge_tgt = rel["entity_b"]
            direction = "mutual"

        edges.append({
            "source": edge_src,
            "target": edge_tgt,
            "weight": rel["weight"],
            "a_to_b": c_a_to_b,
            "b_to_a": c_b_to_a,
            "direction": direction
        })

    # Fetch entity details
    if seen_entities:
        entity_list = list(seen_entities)
        entities_data = await db.async_execute(
            """
            SELECT name, type, total_mentions, sentiment_score
            FROM knowledge_entities
            WHERE name = ANY(%s)
            """,
            (entity_list,),
        )
        
        # Create look-up map
        entity_map = {e["name"]: e for e in entities_data}
        
        for name in entity_list:
            data = entity_map.get(name)
            if data:
                nodes.append({
                    "id": name,
                    "label": name,
                    "type": data["type"] or "ENTITY",
                    "mentions": data["total_mentions"] or 1,
                    "sentiment": float(data["sentiment_score"] or 0.0)
                })
            else:
                nodes.append({
                    "id": name,
                    "label": name,
                    "type": "ENTITY",
                    "mentions": 1,
                    "sentiment": 0.0
                })
    
    result = {
        "status": "success",
        "nodes": nodes,
        "edges": edges
    }
    
    return result


class NodeSynthesisRequest(BaseModel):
    entities: List[str]
    lang: Optional[str] = "sr"


@router.post("/intelligence/synthesize-nodes")
@custom_rate_limit("10/minute")
async def synthesize_nodes(request: Request, payload: NodeSynthesisRequest):
    """
    Local Analyst: Dynamically synthesize a broadsheet intelligence briefing
    for a multi-select group of entities/nodes in recent news.
    """
    entities = [e.strip() for e in payload.entities if e.strip()]
    if not entities:
        return {"status": "error", "message": "Nije izabran nijedan entitet."}

    lang = payload.lang or "sr"

    # Query clusters that mention ANY of the target entities within the last 14 days
    rows = await db.async_execute(
        """
        SELECT DISTINCT cluster_id 
        FROM entity_mentions_daily 
        WHERE entity_name = ANY(%s) AND day >= CURRENT_DATE - INTERVAL '14 days'
        LIMIT 15
        """,
        (entities,),
    )
    
    cluster_ids = [r["cluster_id"] for r in rows]
    if not cluster_ids:
        msg = "Nema nedavnih zabeleženih interakcija u vestima za izabrane entitete u poslednjih 14 dana." if lang == "sr" else "Нема неодамнешни забележани интеракции во вестите за избраните ентитети во последните 14 дена."
        return {
            "status": "success",
            "synthesis": msg,
            "citations": []
        }

    # Fetch top articles from these clusters
    articles = await db.async_execute(
        """
        SELECT title, description, source, link, created_at, cluster_id
        FROM articles
        WHERE cluster_id = ANY(%s)
        ORDER BY created_at DESC
        LIMIT 25
        """,
        (cluster_ids,),
    )

    if not articles:
        msg = "Nema nedavnih članaka za ove entitete." if lang == "sr" else "Нема неодамнешни написи за овие ентитети."
        return {
            "status": "success",
            "synthesis": msg,
            "citations": []
        }

    # Format context for Gemma 2 Local Analyst
    context_lines = []
    citations = []
    for idx, art in enumerate(articles):
        cite_id = idx + 1
        title = art["title"] or ""
        desc = art["description"] or ""
        src = art["source"] or ""
        context_lines.append(f"[{cite_id}] NASLOV: {title} | IZVOR: {src}\nOPIS: {desc}\n")
        citations.append({
            "id": cite_id,
            "title": title,
            "source": src,
            "link": art["link"] or "#"
        })

    context_text = "\n".join(context_lines)

    # Construct LLM prompt
    from nlp.local_analyst import analyst
    
    if lang == "sr":
        system_prompt = (
            "Ti si vrhunski politički analitičar za Presek. Napravi sažetu, objektivnu, visoko-profesionalnu sintezu "
            "interakcija, sukoba ili saveza između sledećih entiteta: " + ", ".join(entities) + ".\n"
            "Koristi isključivo priloženi novinski kontekst. Citiraj izvore koristeći brojeve u formatu [1], [2], itd.\n"
            "Odgovori ISKLJUČIVO na srpskom jeziku (ekavica). Piši u stilu ozbiljne analize (New York Times stil)."
        )
    else:
        system_prompt = (
            "Ти си врвен политички аналитичар за Пресек. Направи концизна, објективна, високо-професионална синтеза "
            "на интеракциите, конфликтите или сојузите меѓу следниве ентитети: " + ", ".join(entities) + ".\n"
            "Користи го исклучиво приложениот контекст од вести. Цитирај ги изворите користејќи броеви во формат [1], [2], итн.\n"
            "Одговори ИСКЛУЧИВО на стандарден литературен македонски јазик. Пиши во стил на сериозна анализа."
        )

    prompt = f"ENTITETI: {', '.join(entities)}\n\nKONTEKST VESTI:\n{context_text[:6000]}"

    try:
        synthesis_text = analyst.analyze(prompt, system_prompt, max_tokens=768, lang=lang, lock_timeout=15)
    except Exception as e:
        log.error(f"[analyst] Group synthesis failed: {e}")
        synthesis_text = f"Greška prilikom analize lokalnog modela: {e}"

    if not synthesis_text:
        synthesis_text = "Nije bilo moguće generisati analizu." if lang == "sr" else "Не беше можно да се генерира анализа."

    return {
        "status": "success",
        "synthesis": synthesis_text,
        "citations": citations
    }


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
    from nlp.local_analyst import analyst

    # Get cluster context
    row = await db.async_execute_one(
        """
        SELECT summary, generated_article
        FROM cluster_summaries WHERE cluster_id = %s
    """,
        (cluster_id,),
    )

    if not row:
        raise HTTPException(status_code=404, detail="klaster nije pronadjen")

    context = f"{row['summary']}\n{row['generated_article']}"
    res = analyst.research_query(q, context)

    return {
        "status": "success",
        "answer": res.get("answer"),
        "suggestions": res.get("suggestions", []),
    }


@router.get("/intelligence/top-entities")
async def get_top_entities(limit: int = 10, lang: Optional[str] = "sr"):
    cache_key = f"api:top-entities:{limit}:{lang}"
    cached = cached_response(cache_key)
    if cached:
        return cached
    fetch_limit = max(limit * 6, 40)
    target_country = "MK" if lang == "mk" else "RS"
    rows = await db.async_execute(
        f"""
        SELECT tag AS name, COUNT(*) AS total_mentions
        FROM (
            SELECT cm.cluster_id, UNNEST(cm.tags) AS tag
            FROM cluster_metadata cm
            JOIN articles a ON a.cluster_id = cm.cluster_id
            WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '48 hours'
              AND a.country = %s
              AND cm.tags IS NOT NULL
            GROUP BY cm.cluster_id, tag
        ) t
        GROUP BY tag
        ORDER BY total_mentions DESC LIMIT %s
        """,
        (
            target_country,
            fetch_limit,
        ),
    )
    aggregated = {}
    for row in rows:
        norm = normalize_person_surface_name(normalize_tag_name(normalize_entity_name(row["name"])))
        if not _is_valid_focus_entity(norm, None):
            continue
        
        if lang == "mk":
            norm = transliterate_lat_to_cyr(norm)
            
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
async def get_live_map(lang: Optional[str] = "sr"):
    country_filter = "MK" if lang == "mk" else "RS"
    return {
        "status": "success",
        "data": await db.async_execute(
            f"SELECT a.source, COUNT(*) as activity_score FROM articles a WHERE a.country = %s AND {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' GROUP BY a.source ORDER BY activity_score DESC",
            (country_filter,),
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

    if interest_vector and isinstance(interest_vector, list) and len(interest_vector) == 384:
        user_vectors.append(interest_vector)

    if recent_ids:
        rows = await db.async_execute(
            "SELECT embedding FROM articles WHERE cluster_id = ANY(%s) AND embedding IS NOT NULL LIMIT 20",
            (recent_ids,),
        )
        for r in rows:
            if r["embedding"]:
                user_vectors.append(
                    json.loads(r["embedding"]) if isinstance(r["embedding"], str) else list(r["embedding"])
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
        s_row = await db.async_execute_one("SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cid,))
        m_row = await db.async_execute_one(
            "SELECT representative_image FROM cluster_metadata WHERE cluster_id = %s",
            (cid,),
        )
        formatted.append(
            {
                "cluster_id": cid,
                "articles": arts,
                "representative_image": (m_row["representative_image"] if m_row else None),
                "score": score_cluster(arts),
                "has_synthesis": bool(s_row and s_row["summary"]),
                "is_breaking": any(a.get("is_breaking") for a in arts),
                "reason": "Predlog za Vas",
            }
        )
    return {"status": "success", "clusters": formatted}


@router.get("/intelligence/briefing")
async def get_latest_briefing(date: Optional[str] = None, lang: str = "sr"):
    """Fetch the latest or specific AI-generated daily briefing."""
    if date:
        from .security import validate_date

        validate_date(date)
        row = await db.async_execute_one("SELECT * FROM daily_briefings WHERE date = %s AND lang = %s", (date, lang))
    else:
        row = await db.async_execute_one(
            "SELECT * FROM daily_briefings WHERE lang = %s ORDER BY date DESC LIMIT 1", (lang,)
        )

    if not row:
        return {"status": "error", "message": "Брифингот не е пронајден" if lang == "mk" else "Brifing nije pronađen"}

    target_date = row["date"]
    target_country = "MK" if lang == "mk" else "RS"

    # 1. Fetch metadata for the sidebar with country filtering and proper daily aggregation
    async def fetch_briefing_entities(entity_type, limit):
        # We look at tags in clusters created on that day for that country
        rows = await db.async_execute(
            """
            SELECT t.name, COUNT(DISTINCT t.cluster_id) as daily_mentions
            FROM (
                SELECT UNNEST(cm.tags) as name, cm.cluster_id
                FROM cluster_metadata cm
                JOIN articles a ON cm.cluster_id = a.cluster_id
                WHERE a.country = %s AND a.created_at >= %s::date AND a.created_at < %s::date + INTERVAL '1 day'
            ) t
            JOIN knowledge_entities ke ON t.name = ke.name
            WHERE ke.type = %s
            GROUP BY t.name
            ORDER BY daily_mentions DESC LIMIT 20
        """,
            (target_country, target_date, target_date, entity_type),
        )
        
        processed = []
        seen = set()
        for r in rows:
            name = normalize_person_surface_name(normalize_tag_name(normalize_entity_name(r["name"])))
            if not _is_valid_focus_entity(name, entity_type):
                continue
            if lang == "mk":
                name = transliterate_lat_to_cyr(name)
            
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            processed.append({"name": name, "total_mentions": r["daily_mentions"]})
            if len(processed) >= limit:
                break
        return processed

    subjects = await fetch_briefing_entities("PERSON", 6)
    locations = await fetch_briefing_entities("GPE", 8)

    # 2. Historical dates for navigation
    historical = await db.async_execute("SELECT date::text as day FROM daily_briefings ORDER BY date DESC LIMIT 14")

    # 3. Lead cluster for the day (filtered by country)
    lead_cluster = await db.async_execute_one(
        """
        SELECT s.cluster_id, s.synthetic_headline, m.representative_image
        FROM cluster_summaries s
        JOIN cluster_metadata m ON s.cluster_id = m.cluster_id
        JOIN articles a ON s.cluster_id = a.cluster_id
        WHERE a.country = %s AND a.created_at >= %s::date AND a.created_at < %s::date + INTERVAL '1 day'
          AND s.lang = %s
        GROUP BY s.cluster_id, s.synthetic_headline, m.representative_image, s.pluralism_score
        ORDER BY s.pluralism_score DESC, COUNT(a.id) DESC
        LIMIT 1
    """,
        (target_country, target_date, target_date, lang),
    )

    # Fetch stats for that day
    stats_res = await db.async_execute_one(
        """
        SELECT
            COUNT(*) as total_articles,
            COUNT(DISTINCT source) as total_sources
        FROM articles
        WHERE country = %s AND created_at >= %s::date AND created_at < %s::date + INTERVAL '1 day'
    """,
        (target_country, target_date, target_date),
    )

    return {
        "status": "success",
        "date": target_date,
        "content": row["content"],
        "metadata": row.get("metadata") or {},
        "subjects": subjects,
        "locations": locations,
        "historical_dates": historical,
        "lead_cluster": lead_cluster,
        "day_stats": stats_res,
    }

from routes.security import admin_auth

@router.post("/intelligence/save-insight")
async def save_insight(request: Request, authorized: str = Depends(admin_auth)):
    """Saves a research insight for an authenticated user."""
    data = await request.json()
    cluster_id = data.get("cluster_id")
    title = data.get("title")
    report = data.get("report")
    
    from core.database import db_manager as db
    
    # Use asynchronous execution to prevent blocking the worker thread
    await db.async_execute(
        "INSERT INTO saved_insights (user_id, cluster_id, title, report) VALUES (%s, %s, %s, %s)",
        (authorized, cluster_id, title, report),
        fetch=False
    )
    
    return {"status": "success", "message": "Insight saved successfully."}

@router.get("/intelligence/briefing/audio")
async def get_briefing_audio(date: Optional[str] = None, lang: str = "sr"):
    """Generates or fetches the daily briefing TTS audio and returns its public URL."""
    if date:
        from .security import validate_date
        validate_date(date)
        row = await db.async_execute_one(
            "SELECT content, date FROM daily_briefings WHERE date = %s AND lang = %s", (date, lang)
        )
    else:
        row = await db.async_execute_one(
            "SELECT content, date FROM daily_briefings WHERE lang = %s ORDER BY date DESC LIMIT 1", (lang,)
        )

    if not row or not row.get("content"):
        return {"status": "error", "message": "Briefing content not found"}

    target_date = str(row["date"])
    content = str(row["content"])

    from core.audio_service import AudioService
    loop = asyncio.get_event_loop()
    audio_url = await loop.run_in_executor(
        None, AudioService.generate_briefing_audio, target_date, content, lang
    )

    if not audio_url:
        return {"status": "error", "message": "Failed to synthesize audio briefing."}

    return {"status": "success", "audio_url": audio_url}

