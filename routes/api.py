from __future__ import annotations
import datetime
import re
import json
import os
import time
import urllib.request
import urllib.error
import traceback
from collections import defaultdict

from flask import Blueprint, jsonify, request, Response
from database import get_db
from utils import score_cluster, rank_articles_in_cluster, cached_response, set_cache
from config import BREAKING_SCORE_THRESHOLD, SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY

api_bp = Blueprint('api', __name__)

@api_bp.route("/api/news")
def api_news():
    page      = request.args.get("page", 0, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    country   = request.args.get("country", "🇲🇰")
    sub       = request.args.get("sub", "").strip()
    ids       = request.args.get("ids", "").strip()
    sort_by   = request.args.get("sort", "recent")
    topic     = request.args.get("topic", "").strip()
    sentiment = request.args.get("sentiment", "").strip()
    
    # Personalized Follows
    follow_sources = request.args.get("follow_sources", "").strip()
    follow_topics  = request.args.get("follow_topics", "").strip()
    
    page_size = min(page_size, 100)
    
    cache_key = f"news:{country}:{sub}:{ids}:{sort_by}:{topic}:{sentiment}:{follow_sources}:{follow_topics}:{page}:{page_size}"
    cached = cached_response(cache_key, ttl=30)
    if cached: return jsonify(cached)
    
    conn = get_db()
    if ids:
        # Fetch specific clusters (Bookmarks)
        cluster_ids = [cid.strip() for cid in ids.split(',') if cid.strip()]
        rows = conn.execute(
            "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
            (cluster_ids,)
        ).fetchall()
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
            if country and country != '🇲🇰':
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
            
        sql += " ORDER BY created_at DESC LIMIT 500"
        rows = conn.execute(sql, tuple(params)).fetchall()
    
    # Synthesis cache
    synthesis_rows = conn.execute("SELECT cluster_id FROM cluster_summaries").fetchall()
    cached_synthesis_ids = {r["cluster_id"] for r in synthesis_rows}
    
    # Group by cluster
    clusters = defaultdict(list)
    for r in rows:
        clusters[r['cluster_id']].append(dict(r))

    # Fetch all reactions for these clusters
    cluster_ids_found = list(clusters.keys())
    reactions_map = defaultdict(lambda: defaultdict(int))
    if cluster_ids_found:
        react_rows = conn.execute("SELECT cluster_id, emoji, count FROM reactions WHERE cluster_id = ANY(%s)", (cluster_ids_found,)).fetchall()
        for rr in react_rows:
            reactions_map[rr["cluster_id"]][rr["emoji"]] = rr["count"]

    conn.close()

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
            "reactions":     reactions_map.get(cid, {}),
            "is_breaking":   s >= BREAKING_SCORE_THRESHOLD,
            "has_summary":   any(a.get("summary") for a in arts),
            "has_synthesis": cid in cached_synthesis_ids,
        })

    start  = page * page_size
    end    = start + page_size
    paged  = result[start:end]
    result_data = {
        "clusters":    paged,
        "page":        page,
        "page_size":   page_size,
        "total":       len(result),
        "has_more":    end < len(result),
    }
    set_cache(cache_key, result_data, ttl=60)
    return jsonify(result_data)


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
    row = conn.execute("SELECT * FROM articles WHERE id = %s", (article_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Article not found"}), 404
    
    if row["summary"]:
        conn.close()
        return jsonify({"summary": row["summary"]})
    
    from ai_engine import summarize_to_macedonian
    summary = summarize_to_macedonian(row["title"])
    if summary:
        conn.execute("UPDATE articles SET summary = %s WHERE id = %s", (summary, article_id))
        conn.commit()
    conn.close()
    return jsonify({"summary": summary})


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
    
    from config import GEMINI_URL, GOOGLE_API_KEY
    from prompts import ANALYSIS_SYSTEM_PROMPT
    
    payload = {
        "system_instruction": {"parts": [{"text": ANALYSIS_SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": f"Analyze these stories:\n{context_text}"}]}]
    }
    try:
        req = urllib.request.Request(f"{GEMINI_URL}?key={GOOGLE_API_KEY}", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            answer = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify({"analysis": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/trending")
def api_trending():
    from trending import get_trending
    from config import DB_PATH
    cached = cached_response("trending", ttl=120)
    if cached: return jsonify(cached)
    
    results = get_trending(DB_PATH)
    set_cache("trending", results, ttl=120)
    return jsonify(results)


@api_bp.route("/api/stats/full")
def api_stats_full():
    from config import DB_PATH, RSS_FEEDS
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

        db_size = os.path.getsize(DB_PATH) / (1024*1024) if os.path.exists(DB_PATH) else 0
        uptime_s = int(time.time() - health._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, _   = divmod(rem, 60)

        return jsonify({
            "uptime": f"{h}ч {m}м",
            "db_size_mb": round(db_size, 2),
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
        # Find relevant news context from last 3 days
        sql = """
            SELECT source, title, description, ts_rank(to_tsvector('simple', title || ' ' || COALESCE(description, '')), q) as rank
            FROM articles, plainto_tsquery('simple', %s) q
            WHERE to_tsvector('simple', title || ' ' || COALESCE(description, '')) @@ q
              AND created_at >= NOW() - INTERVAL '3 days'
            ORDER BY rank DESC
            LIMIT 10
        """
        rows = conn.execute(sql, (query,)).fetchall()
        conn.close()
        
        if not rows:
            return jsonify({"response": "За жал, немам информации за оваа тема во последните вести. Можам да одговорам само за актуелни случувања."})
            
        context_items = []
        for r in rows:
            context_items.append(f"SOURCE: {r['source']} | HEADLINE: {r['title']} | DESC: {(r['description'] or '')[:100]}...")
        
        context_text = "\n".join(context_items)
        
        from prompts import GLOBAL_ASSISTANT_SYSTEM_PROMPT
        from config import GOOGLE_API_KEY, GEMINI_URL
        
        payload = {
            "system_instruction": {"parts": [{"text": GLOBAL_ASSISTANT_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": f"NEWS CONTEXT:\n{context_text}\n\nUSER QUESTION: {query}"}]}]
        }
        
        req = urllib.request.Request(f"{GEMINI_URL}?key={GOOGLE_API_KEY}", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            answer = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify({"response": answer})
            
    except Exception as e:
        return jsonify({"error": "Серверот е преоптоварен. Обидете се подоцна."}), 500


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
    
    from prompts import FACTCHECK_SYSTEM_PROMPT
    from config import GOOGLE_API_KEY, GEMINI_URL
    
    payload = {
        "contents": [{"parts": [{"text": f"SYSTEM: {FACTCHECK_SYSTEM_PROMPT}\n\nCONTEXT:\n{context_text}"}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    
    try:
        req = urllib.request.Request(f"{GEMINI_URL}?key={GOOGLE_API_KEY}", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            answer = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return Response(answer, mimetype="application/json")
    except Exception as e:
        return jsonify({"error": "Грешка при проверка на фактите."}), 500


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


@api_bp.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    data = request.json
    email = data.get("email", "").strip().lower()
    if not email or "@" not in email or "." not in email:
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
    conn = get_db()
    # Find most frequent entities in clusters from last 24h
    sql = """
        SELECT e.entity_name, e.entity_type, COUNT(DISTINCT e.cluster_id) as mentions
        FROM cluster_entities e
        JOIN articles a ON e.cluster_id = a.cluster_id
        WHERE a.created_at >= NOW() - INTERVAL '24 hours'
        GROUP BY e.entity_name, e.entity_type
        ORDER BY mentions DESC
        LIMIT 15
    """
    rows = conn.execute(sql).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@api_bp.route("/api/ai/entity_info/<name>")
def api_ai_entity_info(name: str):
    from config import GEMINI_URL, GOOGLE_API_KEY
    
    prompt = f"Дај краток, објективен и информативен опис (максимум 3 реченици) на македонски јазик за: {name}. Ако е личност, кажи ја функцијата. Ако е организација, кажи ја дејноста. Врати само чист текст."
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        req = urllib.request.Request(f"{GEMINI_URL}?key={GOOGLE_API_KEY}", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            answer = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return jsonify({"info": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route("/proxy")
def image_proxy():
    from urllib.parse import urlparse, urlunparse, quote
    url = request.args.get("url", "").strip()
    if not url or not url.startswith(("http://", "https://")): return "", 400
    try:
        p = urlparse(url)
        safe_url = urlunparse(p._replace(path=quote(p.path, safe='/:@!$&\'()*+,;='), query=quote(p.query, safe='=&+%')))
        req = urllib.request.Request(safe_url, headers={"User-Agent": "Mozilla/5.0", "Referer": ""})
        with urllib.request.urlopen(req, timeout=8) as resp:
            r = Response(resp.read(), mimetype=resp.headers.get("Content-Type", "image/jpeg"))
            r.headers["Cache-Control"] = "public, max-age=3600"
            r.headers["X-Content-Type-Options"] = "nosniff"
            return r
    except Exception:
        return "", 404
