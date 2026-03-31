from __future__ import annotations
import datetime
import re
import json
import os
import time
import urllib.request
from collections import defaultdict

from flask import Blueprint, jsonify, request, Response
from database import get_db, get_db_size
from utils import score_cluster, rank_articles_in_cluster, cached_response, set_cache, calculate_reading_time, is_balanced
from config import BREAKING_SCORE_THRESHOLD, SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY
from embeddings import generate_query_embedding

api_bp = Blueprint('api', __name__)

@api_bp.route("/api/news")
def api_news():
    page      = request.args.get("page", 0, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    country   = request.args.get("country", "🇲🇰")
    
    # Fix for double-encoding of emojis in some environments
    try:
        if country:
            # If it's lat1-encoded utf8 bytes disguised as a string
            country_bytes = country.encode('latin-1')
            if b'\xf0\x9f' in country_bytes:
                country = country_bytes.decode('utf-8')
    except Exception:
        pass

    sub       = request.args.get("sub", "").strip()
    ids       = request.args.get("ids", "").strip()
    sort_by   = request.args.get("sort", "recent")
    topic     = request.args.get("topic", "").strip()
    sentiment = request.args.get("sentiment", "").strip()
    q         = request.args.get("q", "").strip()

    # Personalized Follows
    follow_sources = request.args.get("follow_sources", "").strip()
    follow_topics  = request.args.get("follow_topics", "").strip()

    page_size = min(page_size, 100)

    # Validate sentiment to only allow known emoji values
    if sentiment and sentiment not in ('🟢', '🔴', '⚪'):
        sentiment = ''

    cache_key = f"news:{country}:{sub}:{ids}:{sort_by}:{topic}:{sentiment}:{follow_sources}:{follow_topics}:{q}:{page}:{page_size}"
    cached = cached_response(cache_key, ttl=30)
    if cached: return jsonify(cached)

    conn = get_db()
    try:
        if ids:
            # Fetch specific clusters (Bookmarks)
            cluster_ids = [cid.strip() for cid in ids.split(',') if cid.strip()]
            rows = conn.execute(
                "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
                (cluster_ids,)
            ).fetchall()
        elif q:
            # Hybrid search: full-text + semantic vector search
            fts_sql = """
                SELECT *, ts_rank_cd(search_vector, websearch_to_tsquery('simple', %s)) AS rank
                FROM articles
                WHERE search_vector @@ websearch_to_tsquery('simple', %s)
                ORDER BY rank DESC, created_at DESC
                LIMIT 100
            """
            fts_rows = conn.execute(fts_sql, (q, q)).fetchall()

            # Also try semantic search if embeddings exist
            query_vec = generate_query_embedding(q)
            if query_vec:
                vec_sql = """
                    SELECT *, 1 - (embedding <=> %s::vector) as rank
                    FROM articles
                    WHERE embedding IS NOT NULL
                      AND 1 - (embedding <=> %s::vector) > 0.3
                    ORDER BY embedding <=> %s::vector
                    LIMIT 50
                """
                vec_str = str(query_vec)
                vec_rows = conn.execute(vec_sql, (vec_str, vec_str, vec_str)).fetchall()
                # Merge: deduplicate by link
                seen_links = {r['link'] for r in fts_rows}
                merged = list(fts_rows)
                for r in vec_rows:
                    if r['link'] not in seen_links:
                        merged.append(r)
                        seen_links.add(r['link'])
                rows = merged
            else:
                rows = fts_rows
        else:
            sql = "SELECT * FROM articles WHERE 1=1"
            params = []

            if follow_sources or follow_topics:
                # Personalized "For Me" logic
                sub_clauses = []
                if follow_sources:
                    sources_list = [s.strip() for s in follow_sources.split(',') if s.strip()]
                    sub_clauses.append("source = ANY(%s)")
                    params.append(sources_list)
                if follow_topics:
                    topics_list = [t.strip() for t in follow_topics.split(',') if t.strip()]
                    sub_clauses.append("topic = ANY(%s)")
                    params.append(topics_list)

                if sub_clauses:
                    sql += " AND (" + " OR ".join(sub_clauses) + ")"
            else:
                # Regular Filters
                if country:
                    sql += " AND country = %s"
                    params.append(country)
                if sub:
                    sql += " AND subcategory = %s"
                    params.append(sub)
                if topic:
                    sql += " AND topic = %s"
                    params.append(topic)

            if sentiment:
                sql += " AND summary LIKE %s"
                params.append(f"%{sentiment}%")

            # Fetch enough articles to fill requested page (estimate: page_size * 3 articles per cluster)
            # but always fetch at least 200 to ensure accurate scoring
            fetch_limit = max(200, (page + 1) * page_size * 3)
            fetch_limit = min(fetch_limit, 500)
            sql += f" ORDER BY created_at DESC LIMIT {fetch_limit}"
            rows = conn.execute(sql, tuple(params)).fetchall()

        # Group by cluster and add reading time
        clusters = defaultdict(list)
        for r in rows:
            d = dict(r)
            d['reading_time'] = calculate_reading_time(d.get('description', ''))
            clusters[r['cluster_id']].append(d)

        cluster_ids_found = list(clusters.keys())

        # Synthesis cache for only the clusters found
        cached_synthesis_ids = set()
        if cluster_ids_found:
            s_rows = conn.execute("SELECT cluster_id FROM cluster_summaries WHERE cluster_id = ANY(%s)", (cluster_ids_found,)).fetchall()
            cached_synthesis_ids = {r["cluster_id"] for r in s_rows}

        ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]

        if sort_by == 'popular':
            sorted_clusters = sorted(ranked_clusters, key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        else:
            sorted_clusters = sorted(ranked_clusters, key=score_cluster, reverse=True)

        result = []
        for arts in sorted_clusters:
            s   = score_cluster(arts)
            cid = arts[0]["cluster_id"] if arts else None
            total_clicks = sum(a.get("clicks", 0) or 0 for a in arts)
            result.append({
                "articles":      arts,
                "score":         round(s, 3),
                "clicks":        total_clicks,
                "cluster_id":    cid,
                "is_breaking":   s >= BREAKING_SCORE_THRESHOLD,
                "has_summary":   any(a.get("summary") for a in arts),
                "has_synthesis": cid in cached_synthesis_ids,
                "has_balanced":  is_balanced(arts),
            })

        start  = page * page_size
        end    = start + page_size
        paged  = result[start:end]

        # Fetch reactions only for the paginated clusters
        reactions_map = defaultdict(lambda: defaultdict(int))
        paged_cids = [c["cluster_id"] for c in paged if c["cluster_id"]]
        if paged_cids:
            react_rows = conn.execute("SELECT cluster_id, emoji, count FROM reactions WHERE cluster_id = ANY(%s)", (paged_cids,)).fetchall()
            for rr in react_rows:
                reactions_map[rr["cluster_id"]][rr["emoji"]] = rr["count"]
        for c in paged:
            c["reactions"] = reactions_map.get(c["cluster_id"], {})

        result_data = {
            "clusters":    paged,
            "page":        page,
            "page_size":   page_size,
            "total":       len(result),
            "has_more":    end < len(result),
        }
        set_cache(cache_key, result_data, ttl=60)
        return jsonify(result_data)
    except Exception as e:
        import logging
        logging.getLogger("presek").error(f"[api/news] {e}")
        return jsonify({"clusters": [], "page": page, "page_size": page_size, "total": 0, "has_more": False, "error": "Серверска грешка"}), 500
    finally:
        conn.close()


@api_bp.route("/api/scores")
def api_scores():
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles ORDER BY created_at DESC LIMIT 250").fetchall()
    conn.close()
    clusters = defaultdict(list)
    for r in rows:
        clusters[r['cluster_id']].append(dict(r))
    result = []
    for arts in clusters.values():
        arts = rank_articles_in_cluster(arts)
        result.append({
            "headline": arts[0]["title"][:60],
            "sources": [a["source"] for a in arts],
            "score": round(score_cluster(arts), 3),
        })
    result.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(result[:10])


@api_bp.route("/api/summarize/<int:article_id>")
def api_summarize(article_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM articles WHERE id = %s", (article_id,)).fetchone()
        if not row:
            return jsonify({"error": "Article not found"}), 404

        if row["summary"]:
            return jsonify({"summary": row["summary"]})

        from ai_engine import _call_ai, clean_json_response
        from prompts import SUMMARY_SYSTEM_PROMPT
        raw, tier = _call_ai(row["title"], SUMMARY_SYSTEM_PROMPT, task_type="summarize")
        summary = None
        if raw:
            cleaned = clean_json_response(raw)
            summary = cleaned.get('summary', str(cleaned)) if isinstance(cleaned, dict) else str(cleaned)
            conn.execute("UPDATE articles SET summary = %s WHERE id = %s", (summary, article_id))
            conn.commit()
        return jsonify({"summary": summary})
    finally:
        conn.close()


@api_bp.route("/api/analyze/<cluster_id>")
def api_analyze(cluster_id: str):
    conn = get_db()
    rows = conn.execute("SELECT source, title, description FROM articles WHERE cluster_id = %s", (cluster_id,)).fetchall()
    conn.close()
    if not rows: return jsonify({"error": "Cluster not found"}), 404

    context_items = []
    for r in rows:
        snippet = (r['description'] or "")[:120] + "..." if r['description'] else "No snippet"
        context_items.append(f"SOURCE: {r['source']}\nHEADLINE: {r['title']}\nSNIPPET: {snippet}")

    context_text = "\n---\n".join(context_items)

    from ai_engine import _call_ai
    from prompts import ANALYSIS_SYSTEM_PROMPT

    answer, tier = _call_ai(f"Analyze these stories:\n{context_text}", ANALYSIS_SYSTEM_PROMPT, max_tokens=2000, task_type="analysis")
    if answer:
        return jsonify({"analysis": answer})
    return jsonify({"error": "AI service unavailable."}), 503


@api_bp.route("/api/briefing")
def api_briefing():
    conn = get_db()
    row = conn.execute("SELECT content, date FROM daily_briefings ORDER BY date DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        return jsonify({"content": row["content"], "date": row["date"].isoformat()})
    return jsonify({"error": "Брифингот сè уште не е генериран за денес."}), 404


@api_bp.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2: return jsonify({"clusters": [], "total": 0})

    conn = get_db()
    try:
        # Hybrid search: combine full-text (keyword) + semantic (vector) results
        article_scores: dict[int, float] = {}  # article_id -> combined score
        article_data: dict[int, dict] = {}

        # 1. Full-text search (keyword matching)
        fts_sql = """
            SELECT *, ts_rank(search_vector, websearch_to_tsquery('simple', %s)) as fts_rank
            FROM articles
            WHERE search_vector @@ websearch_to_tsquery('simple', %s)
            ORDER BY fts_rank DESC
            LIMIT 100
        """
        fts_rows = conn.execute(fts_sql, (q, q)).fetchall()
        for r in fts_rows:
            d = dict(r)
            article_data[r['id']] = d
            article_scores[r['id']] = float(r['fts_rank']) * 10  # weight keyword matches

        # 2. Semantic search (vector similarity)
        query_vec = generate_query_embedding(q)
        if query_vec:
            vec_sql = """
                SELECT *, 1 - (embedding <=> %s::vector) as similarity
                FROM articles
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT 100
            """
            vec_str = str(query_vec)
            vec_rows = conn.execute(vec_sql, (vec_str, vec_str)).fetchall()
            for r in vec_rows:
                d = dict(r)
                sim = float(r['similarity'])
                if sim < 0.3:
                    continue  # skip low-similarity results
                aid = r['id']
                if aid in article_scores:
                    article_scores[aid] += sim * 5  # boost articles found by both methods
                else:
                    article_scores[aid] = sim * 5
                    article_data[aid] = d

        if not article_data:
            return jsonify({"clusters": [], "total": 0})

        # Assign combined score to each article for sorting
        for aid, d in article_data.items():
            d['_search_score'] = article_scores.get(aid, 0)

        # Group by cluster
        clusters = defaultdict(list)
        for d in article_data.values():
            clusters[d["cluster_id"]].append(d)

        ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        sorted_clusters = sorted(ranked, key=lambda arts: max(a.get("_search_score", 0) for a in arts), reverse=True)

        result = []
        for arts in sorted_clusters:
            s = score_cluster(arts)
            result.append({
                "articles":    arts,
                "score":       round(s, 3),
                "cluster_id":  arts[0]["cluster_id"] if arts else None,
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
            })
        return jsonify({"clusters": result, "total": len(result)})
    except Exception as e:
        import logging
        logging.getLogger("presek").error(f"[api/search] {e}")
        return jsonify({"clusters": [], "total": 0, "error": "Грешка при пребарување"}), 500
    finally:
        conn.close()


@api_bp.route("/api/top10")
def api_top10():
    """Alias for news ticker data."""
    conn = get_db()
    try:
        sql = "SELECT * FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC LIMIT 300"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()

    clusters = defaultdict(list)
    for r in rows:
        clusters[r['cluster_id']].append(dict(r))

    ranked = []
    for cid, arts in clusters.items():
        sorted_arts = rank_articles_in_cluster(arts)
        s = score_cluster(sorted_arts)
        ranked.append({
            "cluster_id": cid,
            "articles": sorted_arts,
            "score": s,
            "is_breaking": s >= BREAKING_SCORE_THRESHOLD
        })
    
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(ranked[:10])


@api_bp.route("/api/trending")
def api_trending():
    from trending import get_trending
    cached = cached_response("trending", ttl=120)
    if cached: return jsonify(cached)
    
    results = get_trending()
    set_cache("trending", results, ttl=120)
    return jsonify(results)


@api_bp.route("/api/stats/full")
def api_stats_full():
    from config import RSS_FEEDS
    import health
    try:
        conn = get_db()
        total      = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        by_cat     = conn.execute("SELECT category, COUNT(*) n FROM articles GROUP BY category ORDER BY n DESC").fetchall()
        by_source  = conn.execute("SELECT source, COUNT(*) n FROM articles GROUP BY source ORDER BY n DESC").fetchall()
        recent_24h = conn.execute("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '1 day'").fetchone()[0]
        recent_7d  = conn.execute("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '7 days'").fetchone()[0]
        summarized = conn.execute("SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''").fetchone()[0]
        top_clicks = conn.execute("SELECT title, source, clicks, link FROM articles WHERE clicks > 0 ORDER BY clicks DESC LIMIT 10").fetchall()
        oldest     = conn.execute("SELECT MIN(created_at) FROM articles").fetchone()[0]
        newest     = conn.execute("SELECT MAX(created_at) FROM articles").fetchone()[0]

        # Velocity Data
        velocity_rows = conn.execute("""
            SELECT date_trunc('hour', created_at) as hr, COUNT(*) 
            FROM articles 
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY hr ORDER BY hr ASC
        """).fetchall()
        velocity = [{"t": r[0].isoformat(), "n": r[1]} for r in velocity_rows]

        # Sentiment Index (last 7 days)
        sentiment_rows = conn.execute("""
            SELECT source, summary 
            FROM articles 
            WHERE created_at >= NOW() - INTERVAL '7 days' 
              AND summary IS NOT NULL AND summary != ''
        """).fetchall()

        source_sentiments = defaultdict(list)
        for r in sentiment_rows:
            s = r["summary"]
            score = 0
            if '🟢' in s: score = 1
            elif '🔴' in s: score = -1
            source_sentiments[r["source"]].append(score)

        sentiment_index = []
        for src, scores in source_sentiments.items():
            if len(scores) >= 5: # Only sources with enough data
                avg = sum(scores) / len(scores)
                sentiment_index.append({"source": src, "score": round(avg, 2), "count": len(scores)})

        sentiment_index.sort(key=lambda x: abs(x["score"]), reverse=True)

        # Media Speed (Who reports first?)
        speed_rows = conn.execute("""
            WITH FirstReports AS (
                SELECT source, cluster_id, 
                       ROW_NUMBER() OVER(PARTITION BY cluster_id ORDER BY created_at ASC) as r
                FROM articles
                WHERE created_at >= NOW() - INTERVAL '7 days'
            )
            SELECT source, COUNT(*) as first_count
            FROM FirstReports
            WHERE r = 1
            GROUP BY source
            ORDER BY first_count DESC
            LIMIT 10
        """).fetchall()
        speed_leaderboard = [dict(r) for r in speed_rows]

        # Topic Trends (last 7 days)
        topic_rows = conn.execute("""
            SELECT topic, date_trunc('day', created_at) as day, COUNT(*) 
            FROM articles 
            WHERE created_at >= NOW() - INTERVAL '7 days' AND topic != 'Вести'
            GROUP BY topic, day ORDER BY day ASC
        """).fetchall()

        topic_trends = defaultdict(list)
        for r in topic_rows:
            topic_trends[r[0]].append({"day": r[1].isoformat(), "count": r[2]})

        formatted_trends = [{"topic": k, "data": v} for k, v in topic_trends.items()]

        conn.close()

        # Call get_db_size directly
        current_db_size = get_db_size()

        uptime_s = int(time.time() - health._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, _   = divmod(rem, 60)

        return jsonify({
            "uptime": f"{h}ч {m}м",
            "db_size_mb": current_db_size,
            "total_articles": total,
            "last_24h": recent_24h,
            "last_7d": recent_7d,
            "summarized": summarized,
            "summarized_pct": round(summarized / total * 100, 1) if total else 0,
            "oldest_article": oldest,
            "newest_article": newest,
            "total_feeds": len(RSS_FEEDS),
            "velocity": velocity,
            "sentiment_index": sentiment_index[:15],
            "speed_leaderboard": speed_leaderboard,
            "topic_trends": formatted_trends,
            "by_category": [{"cat": r[0] or "Македонија", "n": r[1]} for r in by_cat],
            "by_source": [{"source": r[0], "n": r[1]} for r in by_source],
            "top_clicked": [{"title": r[0][:70], "source": r[1], "clicks": r[2], "link": r[3]} for r in top_clicks],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route("/api/ai/ask", methods=["POST"])
def api_ai_ask():
    data = request.json
    query = data.get("query", "").strip()
    if not query or len(query) < 3:
        return jsonify({"error": "Ве молиме внесете подолго прашање."}), 400

    try:
        conn = get_db()
        try:
            # 1. Semantic search for recent and synthesized content
            query_vec = generate_query_embedding(query)
            if query_vec:
                # We look for articles AND synthesized summaries to get a broader perspective
                vec_sql = """
                    SELECT a.source, a.title, a.description, cs.summary as synthesis,
                           1 - (a.embedding <=> %s::vector) as rank
                    FROM articles a
                    LEFT JOIN cluster_summaries cs ON a.cluster_id = cs.cluster_id
                    WHERE a.embedding IS NOT NULL
                      AND a.created_at >= NOW() - INTERVAL '7 days'
                    ORDER BY a.embedding <=> %s::vector
                    LIMIT 10
                """
                vec_str = str(query_vec)
                rows = conn.execute(vec_sql, (vec_str, vec_str)).fetchall()
                rows = [r for r in rows if float(r['rank']) > 0.2]
            else:
                # Fallback to keyword search
                fts_sql = """
                    SELECT source, title, description, NULL as synthesis,
                           ts_rank(search_vector, plainto_tsquery('simple', %s)) as rank
                    FROM articles
                    WHERE search_vector @@ plainto_tsquery('simple', %s)
                      AND created_at >= NOW() - INTERVAL '7 days'
                    ORDER BY rank DESC
                    LIMIT 10
                """
                rows = conn.execute(fts_sql, (query, query)).fetchall()
        finally:
            conn.close()

        if not rows:
            return jsonify({"response": "За жал, немам информации за оваа тема во моите извори од последната недела."})

        # 2. Build Rich Context
        context_items = []
        seen_synthesis = set()
        for r in rows:
            item = f"SOURCE: {r['source']} | HEADLINE: {r['title']}"
            if r['synthesis'] and r['synthesis'] not in seen_synthesis:
                item += f"\nSYNTHESIS: {r['synthesis']}"
                seen_synthesis.add(r['synthesis'])
            else:
                item += f"\nDESC: {(r['description'] or '')[:150]}..."
            context_items.append(item)

        context_text = "\n---\n".join(context_items)

        from ai_engine import _call_ai
        from prompts import GLOBAL_ASSISTANT_SYSTEM_PROMPT

        # We use a slightly more powerful prompt for RAG v2
        advanced_prompt = (
            GLOBAL_ASSISTANT_SYSTEM_PROMPT + 
            "\n\nДОПОЛНИТЕЛНО: Ако забележиш спротивставени информации меѓу изворите, нагласи ги. "
            "Ако има синтетизирана анализа (SYNTHESIS), дај ѝ приоритет на неа за сеопфатен одговор."
        )

        answer, tier = _call_ai(f"КОНТЕКСТ ОД ВЕСТИ:\n{context_text}\n\nПРАШАЊЕ НА КОРИСНИКОТ: {query}", advanced_prompt, max_tokens=2000, task_type="ai_ask")
        if answer:
            return jsonify({"response": answer, "sources_count": len(rows)})
        return jsonify({"error": "Серверот е преоптоварен. Обидете се подоцна."}), 503

    except Exception as e:
        import logging
        logging.getLogger("presek").error(f"[api/ai/ask] {e}")
        return jsonify({"error": "Грешка при обработка на прашањето."}), 500

@api_bp.route("/api/chat_cluster", methods=["POST"])
def api_chat_cluster():
    data = request.json
    cid = data.get("cluster_id")
    query = data.get("query", "").strip()
    
    if not cid or not query:
        return jsonify({"error": "Невалидно прашање."}), 400
        
    conn = get_db()
    rows = conn.execute("SELECT source, title, description FROM articles WHERE cluster_id = %s", (cid,)).fetchall()
    conn.close()
    
    if not rows:
        return jsonify({"error": "Веста не е пронајдена."}), 404
        
    context_items = []
    for r in rows:
        context_items.append(f"ИЗВОР: {r['source']} | НАСЛОВ: {r['title']} | ОПИС: {r['description'] or ''}")
    
    context_text = "\n---\n".join(context_items)
    
    from ai_engine import _call_ai
    system_prompt = "Ти си истражувачки асистент на вести. Врз основа на дадените извори за овој настан, одговори на прашањето на корисникот на македонски јазик. Биди објективен, детален и наведи ги изворите каде што е можно. Ако изворите не содржат информации за прашањето, кажи го тоа."
    
    answer, tier = _call_ai(f"КОНТЕКСТ:\n{context_text}\n\nПРАШАЊЕ: {query}", system_prompt, max_tokens=1500, task_type="ai_ask")
    if answer:
        return jsonify({"response": answer})
    return jsonify({"error": "AI сервисот не е достапен."}), 503

@api_bp.route("/api/ai/factcheck/<cluster_id>")
def api_ai_factcheck(cluster_id: str):
    conn = get_db()
    rows = conn.execute("SELECT source, title, description FROM articles WHERE cluster_id = %s", (cluster_id,)).fetchall()
    conn.close()

    if not rows:
        return jsonify({"error": "Кластерот не е пронајден."}), 404

    context_items = []
    for r in rows:
        context_items.append(f"SOURCE: {r['source']} | TITLE: {r['title']} | DESC: {(r['description'] or '')[:200]}")

    context_text = "\n---\n".join(context_items)

    from ai_engine import _call_ai, clean_json_response
    from prompts import FACTCHECK_SYSTEM_PROMPT

    answer, tier = _call_ai(context_text, FACTCHECK_SYSTEM_PROMPT, max_tokens=2000, json_mode=True, task_type="factcheck")
    if answer:
        return Response(answer, mimetype="application/json")
    return jsonify({"error": "Грешка при проверка на фактите."}), 503


@api_bp.route("/api/react", methods=["POST"])
def api_react():
    data = request.json
    cid = data.get("cluster_id")
    emoji = data.get("emoji")
    allowed = ["👍", "😮", "😡", "😢", "🔥"]
    
    if not cid or emoji not in allowed:
        return jsonify({"error": "Invalid request"}), 400
        
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO reactions (cluster_id, emoji, count) 
            VALUES (%s, %s, 1) 
            ON CONFLICT (cluster_id, emoji) DO UPDATE SET count = reactions.count + 1
        """, (cid, emoji))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/admin/telegram_briefing")
def api_admin_telegram_briefing():
    # Simple security check
    auth = request.args.get("token")
    if auth != os.environ.get("ADMIN_TOKEN"):
        return jsonify({"error": "Unauthorized"}), 401
    
    from tasks import send_telegram_briefing_task
    send_telegram_briefing_task.delay()
    return jsonify({"ok": True, "message": "Telegram briefing task queued."})


@api_bp.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    data = request.json
    email = data.get("email", "").strip().lower()
    # RFC-ish email validation: local@domain.tld, no spaces, reasonable length
    if not email or not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email) or len(email) > 254:
        return jsonify({"error": "Ве молиме внесете валидна е-пошта."}), 400
    
    try:
        conn = get_db()
        conn.execute("INSERT INTO subscribers (email) VALUES (%s) ON CONFLICT DO NOTHING", (email,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "message": "Успешно се претплативте!"})
    except Exception as e:
        return jsonify({"error": "Серверска грешка. Обидете се подоцна."}), 500


@api_bp.route("/api/sources/reliability")
def api_sources_reliability():
    from config import SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY
    return jsonify({
        "mapping": SOURCE_CREDIBILITY,
        "default": DEFAULT_CREDIBILITY
    })


@api_bp.route("/api/trending/entities")
def api_trending_entities():
    from tasks import _normalize_entity
    conn = get_db()
    try:
        sql = """
            SELECT e.entity_name, e.entity_type, COUNT(DISTINCT e.cluster_id) as mentions
            FROM cluster_entities e
            JOIN articles a ON e.cluster_id = a.cluster_id
            WHERE a.created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY e.entity_name, e.entity_type
            ORDER BY mentions DESC
            LIMIT 50
        """
        rows = conn.execute(sql).fetchall()

        # Deduplicate via normalization (merge Latin/Cyrillic variants)
        merged: dict[str, dict] = {}
        for r in rows:
            name, etype = _normalize_entity(r['entity_name'], r['entity_type'])
            key = name.lower()
            if key in merged:
                merged[key]['mentions'] += r['mentions']
            else:
                merged[key] = {'entity_name': name, 'entity_type': etype, 'mentions': r['mentions']}

        results = sorted(merged.values(), key=lambda x: x['mentions'], reverse=True)[:15]
        return jsonify(results)
    except Exception:
        return jsonify([])
    finally:
        conn.close()

@api_bp.route("/api/live")
def api_live():
    """SSE endpoint for real-time news updates."""
    from utils import event_stream
    return Response(event_stream("updates"), mimetype="text/event-stream")

@api_bp.route("/api/heartbeat")
def api_heartbeat():
    """Returns basic health metrics for the UI ticker."""
    from database import get_db
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        recent = conn.execute("SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '1 hour'").fetchone()[0]
        return jsonify({
            "status": "online",
            "total_articles": total,
            "last_hour": recent,
            "time": datetime.datetime.now().isoformat()
        })
    finally:
        conn.close()

def _get_r2_client():
    import boto3
    from config import R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
    if not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        return None
    try:
        return boto3.client(
            service_name="s3",
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto"
        )
    except Exception:
        return None

@api_bp.route("/proxy")
def image_proxy():
    from urllib.parse import urlparse, urlunparse, quote
    import ipaddress, socket, hashlib
    from config import R2_BUCKET_NAME

    url = request.args.get("url", "").strip()
    if not url or not url.startswith(("http://", "https://")): return "", 400

    # 1. Check R2 Cache
    cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    r2 = _get_r2_client()
    if r2:
        try:
            obj = r2.get_object(Bucket=R2_BUCKET_NAME, Key=cache_key)
            data = obj["Body"].read()
            content_type = obj.get("ContentType", "image/jpeg")
            r = Response(data, mimetype=content_type)
            r.headers["Cache-Control"] = "public, max-age=31536000" # Cache for 1 year
            r.headers["X-Cache"] = "HIT-R2"
            return r
        except r2.exceptions.NoSuchKey:
            pass # Continue to fetch
        except Exception:
            pass

    try:
        p = urlparse(url)
        # Block private/internal IPs to prevent SSRF
        hostname = p.hostname or ""
        if not hostname:
            return "", 400
        try:
            resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for family, stype, proto, canonname, sockaddr in resolved:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return "", 403
        except (socket.gaierror, ValueError):
            return "", 400

        safe_url = urlunparse(p._replace(path=quote(p.path, safe='/:@!$&\'()*+,;='), query=quote(p.query, safe='=&+%')))
        req = urllib.request.Request(safe_url, headers={"User-Agent": "Mozilla/5.0", "Referer": ""})
        
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
            # Cap response size at 5MB to prevent abuse
            if len(data) > 5 * 1024 * 1024:
                return "", 413
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            if not content_type.startswith("image/"):
                return "", 400

            # 2. Store in R2 for future requests
            if r2:
                try:
                    r2.put_object(
                        Bucket=R2_BUCKET_NAME,
                        Key=cache_key,
                        Body=data,
                        ContentType=content_type,
                        Metadata={"original_url": url}
                    )
                except Exception:
                    pass

            r = Response(data, mimetype=content_type)
            r.headers["Cache-Control"] = "public, max-age=86400" # 24 hours
            r.headers["X-Content-Type-Options"] = "nosniff"
            r.headers["X-Cache"] = "MISS"
            return r
    except Exception:
        return "", 404
