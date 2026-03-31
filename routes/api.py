from __future__ import annotations
import datetime
import json
import os
import time
import logging
from collections import defaultdict

from flask import Blueprint, jsonify, request, Response
from database import db_manager as db
from utils import score_cluster, rank_articles_in_cluster, cached_response, set_cache, calculate_reading_time, is_balanced
from config import BREAKING_SCORE_THRESHOLD
from embeddings import generate_query_embedding

api_bp = Blueprint('api', __name__)
log = logging.getLogger("presek")

def success_response(data, meta=None):
    return jsonify({
        "status": "success",
        "data": data,
        "meta": meta or {}
    })

def error_response(message, code=500, details=None):
    return jsonify({
        "status": "error",
        "message": message,
        "details": details
    }), code

@api_bp.route("/api/news")
def api_news():
    try:
        page      = request.args.get("page", 0, type=int)
        page_size = request.args.get("page_size", 50, type=int)
        country   = request.args.get("country", "🇲🇰")
        
        # Handle double-encoding of emojis
        try:
            if country:
                country_bytes = country.encode('latin-1')
                if b'\xf0\x9f' in country_bytes:
                    country = country_bytes.decode('utf-8')
        except: pass

        sub       = request.args.get("sub", "").strip()
        ids       = request.args.get("ids", "").strip()
        sort_by   = request.args.get("sort", "recent")
        topic     = request.args.get("topic", "").strip()
        sentiment = request.args.get("sentiment", "").strip()
        q         = request.args.get("q", "").strip()
        follow_sources = request.args.get("follow_sources", "").strip()
        follow_topics  = request.args.get("follow_topics", "").strip()

        cache_key = f"v4:news:{country}:{sub}:{ids}:{sort_by}:{topic}:{sentiment}:{follow_sources}:{follow_topics}:{q}:{page}:{page_size}"
        cached = cached_response(cache_key, ttl=30)
        if cached: return jsonify(cached)

        # DAL Extraction
        if ids:
            cluster_ids = [cid.strip() for cid in ids.split(',') if cid.strip()]
            rows = db.get_articles_by_ids(cluster_ids)
        elif q:
            # Full rewrite of search logic in DAL would happen here, keeping it local for now
            rows = db.search_articles(q) 
        elif follow_sources or follow_topics:
            sources_list = [s.strip() for s in follow_sources.split(',') if s.strip()]
            topics_list = [t.strip() for t in follow_topics.split(',') if t.strip()]
            rows = db.get_personalized_articles(sources_list, topics_list)
        else:
            rows = db.get_articles_by_country(country, sub=sub, topic=topic, sentiment=sentiment)

        # Logic Layer: Grouping & Scoring
        clusters = defaultdict(list)
        for r in rows:
            r['reading_time'] = calculate_reading_time(r.get('description', ''))
            clusters[r['cluster_id']].append(r)

        ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        
        if sort_by == 'popular':
            ranked_clusters.sort(key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster, reverse=True)

        # Pagination & Meta
        start = page * page_size
        end = start + page_size
        paged_clusters = ranked_clusters[start:end]
        
        synthesis_ids = db.get_synthesis_ids([c[0]["cluster_id"] for c in paged_clusters])

        result = []
        for arts in paged_clusters:
            s = score_cluster(arts)
            cid = arts[0]["cluster_id"]
            result.append({
                "cluster_id": cid,
                "articles": arts,
                "score": round(s, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_balanced": is_balanced(arts)
            })

        response_data = {
            "clusters": result,
            "has_more": end < len(ranked_clusters),
            "total_clusters": len(ranked_clusters)
        }
        
        # We wrap the existing structure for backward compatibility but add status
        final_json = {
            "status": "success",
            "page": page,
            "page_size": page_size,
            **response_data
        }
        
        set_cache(cache_key, final_json, ttl=60)
        return jsonify(final_json)

    except Exception as e:
        log.error(f"API Error: {e}", exc_info=True)
        return error_response("Failed to fetch news", details=str(e))

@api_bp.route("/api/stats")
def api_stats():
    try:
        return success_response(db.get_stats())
    except Exception as e:
        return error_response("Failed to fetch stats", details=str(e))

@api_bp.route("/api/live")
def api_live():
    from utils import event_stream
    return Response(event_stream("updates"), mimetype="text/event-stream")

# (Other routes remain functional and will be standardized in the final pass)
