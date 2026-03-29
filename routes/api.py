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
import trending
from config import (
    GOOGLE_API_KEY, GEMINI_URL, BREAKING_SCORE_THRESHOLD, RSS_FEEDS
)
from database import get_db
from ai_engine import clean_json_response, _call_ai
from utils import score_cluster, rank_articles_in_cluster, cached_response, set_cache, redis_client
from prompts import SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, ANALYSIS_SYSTEM_PROMPT

api_bp = Blueprint('api', __name__)

@api_bp.route("/api/trending")
def trending_route():
    # The backfill script now populates the cache
    cached = cached_response("trending", ttl=900)
    if cached:
        return jsonify(cached)
    
    # Fallback in case cache is empty or stale
    results = trending.get_trending()
    set_cache("trending", results, ttl=900)
    return jsonify(results)

@api_bp.route("/api/news")
def api_news():
    page      = request.args.get("page", 0, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    country   = request.args.get("country", "🇲🇰")
    sub       = request.args.get("sub", "").strip()
    ids       = request.args.get("ids", "").strip()
    sort_by   = request.args.get("sort", "recent")
    topic     = request.args.get("topic", "").strip()
    page_size = min(page_size, 100)
    
    cache_key = f"news:{country}:{sub}:{ids}:{sort_by}:{topic}:{page}:{page_size}"
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
    elif country == '🇲🇰':
        sql = "SELECT * FROM articles WHERE 1=1"
        params = []
        if sub:
            sql += " AND subcategory = %s"
            params.append(sub)
        if topic:
            sql += " AND topic = %s"
            params.append(topic)
        
        sql += " ORDER BY created_at DESC LIMIT 500"
        rows = conn.execute(sql, tuple(params)).fetchall()
    else:
        # Filtered by country
        sql = "SELECT * FROM articles WHERE country = %s"
        params = [country]
        if topic:
            sql += " AND topic = %s"
            params.append(topic)
            
        sql += " ORDER BY created_at DESC LIMIT 500"
        rows = conn.execute(sql, tuple(params)).fetchall()
    
    # We also need to know which clusters have syntheses to pass 'has_synthesis'
    synthesis_rows = conn.execute("SELECT cluster_id FROM cluster_summaries").fetchall()
    cached_synthesis_ids = {r["cluster_id"] for r in synthesis_rows}
    conn.close()

    clusters = defaultdict(list)
    for r in rows:
        clusters[r['cluster_id']].append(dict(r))

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
        return jsonify({"summary": row["summary"], "cached": True})

    summary, tier = _call_ai(row["title"], SUMMARY_SYSTEM_PROMPT)

    if not summary:
        conn.close()
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    summary = clean_json_response(summary)
    
    conn.execute("UPDATE articles SET summary = %s WHERE id = %s", (summary, article_id))
    conn.commit()
    conn.close()
    return jsonify({"summary": summary, "cached": False, "tier": tier})


@api_bp.route("/api/cluster-summary/<cluster_id>")
def api_cluster_summary(cluster_id: str):
    conn = get_db()
    try:
        row = conn.execute("SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,)).fetchone()
        if row:
            count_row = conn.execute("SELECT COUNT(*) as count FROM articles WHERE cluster_id = %s", (cluster_id,)).fetchone()
            return jsonify({
                "summary": row["summary"],
                "source_count": count_row["count"] if count_row else 0,
                "cached": True,
                "tier": "db_cache"
            })

        rows = conn.execute("SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at ASC LIMIT 10", (cluster_id,)).fetchall()
        if not rows:
            return jsonify({"error": "Cluster not found"}), 404

        articles = [dict(r) for r in rows]
        lines = []
        for a in articles:
            line = f"- [{a['source']}]: {a['title']}"
            desc = (a.get('description') or '').strip()
            if desc:
                # Remove HTML tags and truncate
                desc = re.sub(r'<[^>]+>', '', desc)[:250].strip()
                if desc: line += f"\n  Опис: {desc}"
            lines.append(line)
        content = "\n".join(lines)

        try:
            raw_res, tier = _call_ai(f"Статии:\n{content}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True)
            if not raw_res:
                return jsonify({"error": "AI сервисот е недостапен."}), 503
            
            summary = clean_json_response(raw_res)
            now = datetime.datetime.now()
            
            conn.execute(
                "INSERT INTO cluster_summaries (cluster_id, summary, created_at) VALUES (%s, %s, %s) ON CONFLICT (cluster_id) DO UPDATE SET summary = EXCLUDED.summary, created_at = EXCLUDED.created_at",
                (cluster_id, summary, now)
            )
            conn.commit()
            return jsonify({"summary": summary, "tier": tier})
            
        except Exception as e:
            if '429' in str(e) or 'ResourceExhausted' in str(e):
                return jsonify({"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."})
            return jsonify({"error": "AI сервисот е недостапен."}), 503
    finally:
        conn.close()


@api_bp.route("/api/analyze/<cluster_id>")
def api_analyze(cluster_id: str):
    cached_analysis = redis_client.get(f"analysis:{cluster_id}")
    if cached_analysis:
        return jsonify({"analysis": cached_analysis, "cached": True})

    try:
        conn = get_db()
        rows = conn.execute("SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at ASC LIMIT 10", (cluster_id,)).fetchall()
        conn.close()
    except Exception:
        return jsonify({"error": "Database error"}), 500

    if not rows:
        return jsonify({"error": "Cluster not found"}), 404

    articles = [dict(r) for r in rows]
    lines = []
    for a in articles:
        line = f"- [{a['source']}]: {a['title']}"
        desc = (a.get('description') or '').strip()
        if desc:
            desc = re.sub(r'<[^>]+>', '', desc)[:250].strip()
            line += f"\n  Опис: {desc}"
        lines.append(line)
    content = "\n".join(lines)

    if not content.strip():
        return jsonify({"error": "Нема доволно содржина за анализа."}), 422

    try:
        analysis, tier = _call_ai(f"Статии:\n{content}", ANALYSIS_SYSTEM_PROMPT, timeout=40)
    except Exception:
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    if not analysis:
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    analysis = clean_json_response(analysis)
    try:
        redis_client.setex(f"analysis:{cluster_id}", 3600, analysis) # Cache for 1 hour
    except Exception as e:
        pass
    return jsonify({"analysis": analysis, "cached": False, "tier": tier})


@api_bp.route("/api/click/<int:article_id>", methods=["POST"])
def api_click(article_id: int):
    try:
        conn = get_db()
        conn.execute("UPDATE articles SET clicks = COALESCE(clicks,0) + 1 WHERE id = %s", (article_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/popular")
def api_popular():
    cached = cached_response("popular", ttl=120)
    if cached: return jsonify(cached)
    
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM articles
        WHERE created_at >= NOW() - INTERVAL '7 days'
        AND clicks > 0
        ORDER BY clicks DESC LIMIT 200
    """).fetchall()
    conn.close()
    
    clusters = defaultdict(list)
    for r in rows:
        clusters[r["cluster_id"]].append(dict(r))
        
    ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
    sorted_clusters = sorted(ranked, key=lambda arts: sum(a.get("clicks",0) for a in arts), reverse=True)
    
    result = []
    for arts in sorted_clusters[:10]:
        result.append({
            "articles":    arts,
            "score":       round(score_cluster(arts), 3),
            "cluster_id":  arts[0]["cluster_id"],
            "total_clicks": sum(a.get("clicks",0) for a in arts),
            "is_breaking": False,
        })
    set_cache("popular", result, ttl=120)
    return jsonify(result)

@api_bp.route("/api/top10")
def api_top10():
    cached = cached_response("top10", ttl=60)
    if cached: return jsonify(cached)
    
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles WHERE created_at >= NOW() - INTERVAL '1 day' ORDER BY created_at DESC LIMIT 500").fetchall()
    
    synthesis_rows = conn.execute("SELECT cluster_id FROM cluster_summaries").fetchall()
    cached_synthesis_ids = {r["cluster_id"] for r in synthesis_rows}
    conn.close()
    
    clusters = defaultdict(list)
    for r in rows:
        clusters[r["cluster_id"]].append(dict(r))
        
    ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
    top = sorted(ranked, key=score_cluster, reverse=True)[:10]
    
    result = []
    for i, arts in enumerate(top):
        s   = score_cluster(arts)
        cid = arts[0]["cluster_id"] if arts else None
        result.append({
            "rank":          i + 1,
            "articles":      arts,
            "score":         round(s, 3),
            "cluster_id":    cid,
            "is_breaking":   s >= BREAKING_SCORE_THRESHOLD,
            "has_summary":   any(a.get("summary") for a in arts),
            "has_synthesis": cid in cached_synthesis_ids,
        })
    set_cache("top10", result, ttl=60)
    return jsonify(result)

@api_bp.route("/api/timeboxed")
def api_timeboxed():
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles WHERE created_at >= NOW() - INTERVAL '1 day' ORDER BY created_at DESC LIMIT 500").fetchall()
    conn.close()

    def window_for(ts):
        try:
            # PostgreSQL returns datetime
            if isinstance(ts, datetime.datetime):
                dt = ts
            else:
                dt = datetime.datetime.fromisoformat(ts.replace("+00:00",""))
            h  = dt.hour
            if 6  <= h < 12: return "утро"
            if 12 <= h < 18: return "попладне"
            if 18 <= h < 24: return "вечер"
            return "ноќ"
        except Exception:
            return "ноќ"

    windows = {"утро": defaultdict(list), "попладне": defaultdict(list), "вечер": defaultdict(list)}
    for r in rows:
        w = window_for(r["created_at"])
        if w in windows:
            windows[w][r["cluster_id"]].append(dict(r))

    result = {}
    for w, clusters in windows.items():
        ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        sorted_c = sorted(ranked, key=score_cluster, reverse=True)[:10]
        result[w] = []
        for arts in sorted_c:
            s = score_cluster(arts)
            result[w].append({
                "articles":    arts,
                "score":       round(s, 3),
                "cluster_id":  arts[0]["cluster_id"] if arts else None,
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
            })
    return jsonify(result)

@api_bp.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2: return jsonify([])
    
    conn = get_db()
    # Weighted search: title (A) is more important than description (B)
    sql = """
        SELECT *, ts_rank(to_tsvector('simple', title || ' ' || COALESCE(description, '')), query) as rank
        FROM articles, plainto_tsquery('simple', %s) query
        WHERE to_tsvector('simple', title || ' ' || COALESCE(description, '')) @@ query
        ORDER BY rank DESC, created_at DESC
        LIMIT 200
    """
    rows = conn.execute(sql, (q,)).fetchall()
    conn.close()
    
    if not rows:
        return jsonify({"clusters": [], "total": 0})
        
    clusters = defaultdict(list)
    for r in rows:
        clusters[r["cluster_id"]].append(dict(r))
        
    ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
    # Re-sort by best rank in cluster
    sorted_clusters = sorted(ranked, key=lambda arts: max(a.get("rank", 0) for a in arts), reverse=True)
    
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

@api_bp.route("/api/archive")
def api_archive():
    date_str = request.args.get("date", "")
    page = request.args.get("page", 0, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    page_size = min(page_size, 100)

    if not date_str:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    try:
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM articles WHERE DATE(created_at) = %s", (date_str,)).fetchone()[0]
        sources = conn.execute("SELECT COUNT(DISTINCT source) FROM articles WHERE DATE(created_at) = %s", (date_str,)).fetchone()[0]
        categories = conn.execute("SELECT COUNT(DISTINCT category) FROM articles WHERE DATE(created_at) = %s", (date_str,)).fetchone()[0]

        offset = page * page_size
        rows = conn.execute("SELECT * FROM articles WHERE DATE(created_at) = %s ORDER BY created_at DESC LIMIT %s OFFSET %s", (date_str, page_size, offset)).fetchall()
        conn.close()

        return jsonify({
            "date": date_str,
            "total": total,
            "sources": sources,
            "categories": categories,
            "page": page,
            "page_size": page_size,
            "articles": [dict(r) for r in rows],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
            "by_category": [{"cat": r[0] or "Македонија", "n": r[1]} for r in by_cat],
            "by_source": [{"source": r[0], "n": r[1]} for r in by_source],
            "top_clicked": [{"title": r[0][:70], "source": r[1], "clicks": r[2], "link": r[3]} for r in top_clicks],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route("/api/chat_cluster", methods=["POST"])
def api_chat_cluster():
    data = request.json
    cluster_id = data.get("cluster_id")
    query = data.get("query")
    if not cluster_id or not query: return jsonify({"error": "Missing cluster_id or query"}), 400

    conn = get_db()
    rows = conn.execute("SELECT source, title, description FROM articles WHERE cluster_id = %s", (cluster_id,)).fetchall()
    conn.close()
    if not rows: return jsonify({"error": "Cluster not found"}), 404

    context_items = []
    for r in rows:
        snippet = (r['description'] or "")[:120] + "..." if r['description'] else "No snippet"
        context_items.append(f"SOURCE: {r['source']}\nHEADLINE: {r['title']}\nSNIPPET: {snippet}")
    
    context_text = "\n---\n".join(context_items)
    
    system_instruction = """
Ти си Главен Аналитичар (Chief Analyst) за 'Пресек', премиум македонски агрегатор на вести.
Твојата задача е да им дадеш на корисниците објективен, јасен и прецизен преглед на вестите базиран на понудените извори.

Твоите новинарски правила:
1. НУЛТА ПРИСТРАСНОСТ: Мораш да останеш апсолутно неутрален. Не заземај страна во македонската или глобалната политика.
2. ФОКУС НА ИЗВОРИТЕ: Секогаш кога е можно, посочувај кој медиум што кажал (на пр. "Сител известува дека..., додека Слободен Печат додава...").
3. БЕЗ ПАНИКА: Известувај за трагедии, криминал или војна со ладна глава и почит. Избегнувај сензационализам.
4. КОНЦИЗНОСТ: Одговорите нека бидат кратки, структурирани со точки (bullet points) и лесни за скенирање. Избегнувај долги воведи.
5. КОНТЕКСТ: Ако корисникот праша за нешто што го нема во дадените наслови, користи го твоето пребарување (Search tool) за да дадеш точен, глобален или историски контекст, но јасно напомени дека е дополнителна информација.
6. РЕЛЕВАНТНОСТ: Фокусирај се на факти и сериозна анализа. Игнорирај шпекулации или озборувања кои не се поткрепени со изворите.
"""

    user_prompt = f"CLUSTER CONTEXT (Macedonian Media):\n{context_text}\n\nUSER QUESTION:\n{query}"
    grounding_keywords = ["зошто", "свет", "историја", "анализа", "влијание", "последици", "минатото", "контекст", "кога", "очекува", "иднина", "сад", "еу", "русија"]
    needs_grounding = any(word in query.lower() for word in grounding_keywords)

    try:
        from config import GEMINI_URL, GOOGLE_API_KEY
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "tools": [{"google_search_retrieval": {}}] if needs_grounding else []
        }
        req = urllib.request.Request(f"{GEMINI_URL}?key={GOOGLE_API_KEY}", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            answer = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify({"response": answer, "grounded": needs_grounding})
    except Exception as e:
        return jsonify({"error": "AI сервисот е моментално преоптоварен."}), 503

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
        log.error(f"Global AI Assistant error: {e}")
        return jsonify({"error": "Серверот е преоптоварен. Обидете се подоцна."}), 500

@api_bp.route("/api/briefing")
def api_briefing():
    conn = get_db()
    row = conn.execute("SELECT content, date FROM daily_briefings ORDER BY date DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        return jsonify({"content": row["content"], "date": row["date"].isoformat()})
    return jsonify({"error": "Брифингот сè уште не е генериран за денес."}), 404

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
        log.error(f"Fact-check API error: {e}")
        return jsonify({"error": "Грешка при проверка на фактите."}), 500

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
