from __future__ import annotations
import datetime
import json
import os
import threading
import time
import urllib.request
import urllib.error
import traceback
from collections import defaultdict

from flask import Flask, jsonify, render_template, request, Response
from flask_cors import CORS
from flask_compress import Compress

import health
import trending
from notifier import BreakingNewsNotifier
import digest as digest_module

# Import modularized components
from config import (
    DB_PATH, GOOGLE_API_KEY, NTFY_TOPIC, GEMINI_URL,
    REFRESH_INTERVAL, BREAKING_SCORE_THRESHOLD, RSS_FEEDS,
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, ANALYSIS_SYSTEM_PROMPT
)
from database import get_db, init_db, prune_db, log
from ingestion import ingest_feeds, ingest_diaspora_feeds
from ai_engine import clean_json_response, _call_gemini, _call_ai, auto_summarize_top_clusters
from utils import score_cluster, rank_articles_in_cluster

# Simple time-based response cache
_response_cache: dict[str, tuple[float, any]] = {}

def cached_response(key: str, ttl: int = 60):
    if key in _response_cache:
        ts, val = _response_cache[key]
        if time.time() - ts < ttl:
            return val
    return None

def set_cache(key: str, val):
    _response_cache[key] = (time.time(), val)

# Simple rate limiter
_rate_limits: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 60     # requests per window

def check_rate_limit(ip: str) -> bool:
    now = time.time()
    if ip not in _rate_limits:
        _rate_limits[ip] = []
    _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[ip].append(now)
    return True

app = Flask(__name__)
CORS(app)
Compress(app)

@app.before_request
def rate_limit_check():
    if request.path in ('/', '/favicon.ico') or request.path.startswith('/static'):
        return None
    if request.headers.get("X-Forwarded-For"):
        ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()
    else:
        ip = request.remote_addr or '0.0.0.0'
    if not check_rate_limit(ip):
        return jsonify({"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."}), 429

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

ntfy = BreakingNewsNotifier(topic=NTFY_TOPIC, threshold=3)

# On-demand deep analysis cache (in-memory only, resets on restart)
_analysis_cache: dict[str, str] = {}

_prune_counter = 0
_digest_counter = 0

def ingest_loop():
    global _prune_counter, _digest_counter
    while True:
        try:
            log.info("Fetching RSS feeds...")
            new_count, errors = ingest_feeds()
            health.record_refresh(new_count, errors)
            log.info(f"Added {new_count} new articles, {len(errors)} errors.")
            
            diaspora_count, diaspora_errors = ingest_diaspora_feeds()
            log.info(f"[diaspora] Added {diaspora_count} articles, {len(diaspora_errors)} errors.")
            
            _prune_counter += 1
            if _prune_counter >= 96:
                prune_db()
                _prune_counter = 0
                
            _digest_counter += 1
            if _digest_counter >= 96:
                try:
                    digest_module.generate_digest(
                        db_path=DB_PATH,
                        days=1,
                        save_path=os.path.expanduser("~/presek/digests/digest.html"),
                        ntfy_topic=NTFY_TOPIC,
                    )
                except Exception as _de:
                    log.error(f"Digest failed: {_de}")
                _digest_counter = 0
            
            conn = get_db()
            rows = conn.execute("SELECT * FROM articles ORDER BY created_at DESC LIMIT 500").fetchall()
            conn.close()
            cmap = defaultdict(list)
            for r in rows: cmap[r["cluster_id"]].append(dict(r))
            ntfy.check_and_notify([{"cluster_id": cid, "articles": arts} for cid, arts in cmap.items()])

            auto_summarize_top_clusters(rank_articles_in_cluster, score_cluster)
            
        except Exception as e:
            log.error(f"Ingest loop failed: {e}", exc_info=True)
        log.info(f"Ingest loop sleeping for {REFRESH_INTERVAL}s...")
        time.sleep(REFRESH_INTERVAL)


health.register_health_routes(app, DB_PATH)
trending.register_trending_route(app, DB_PATH)

# =====================================================================
# API ROUTES
# =====================================================================

@app.route("/api/news")
def api_news():
    page      = request.args.get("page", 0, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    country   = request.args.get("country", "🇲🇰")
    page_size = min(page_size, 100)
    cache_key = f"news:{country}:{page}:{page_size}"
    cached = cached_response(cache_key, ttl=30)
    if cached: return jsonify(cached)
    
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE country = ? ORDER BY created_at DESC LIMIT 500",
        (country,)
    ).fetchall()
    
    # We also need to know which clusters have syntheses to pass 'has_synthesis'
    synthesis_rows = conn.execute("SELECT cluster_id FROM cluster_summaries").fetchall()
    cached_synthesis_ids = {r["cluster_id"] for r in synthesis_rows}
    conn.close()

    clusters = defaultdict(list)
    for r in rows:
        clusters[r['cluster_id']].append(dict(r))

    ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]
    sorted_clusters = sorted(ranked_clusters, key=score_cluster, reverse=True)

    result = []
    for arts in sorted_clusters:
        s   = score_cluster(arts)
        cid = arts[0]["cluster_id"] if arts else None
        result.append({
            "articles":      arts,
            "score":         round(s, 3),
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
    set_cache(cache_key, result_data)
    return jsonify(result_data)


@app.route("/api/scores")
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


@app.route("/api/summarize/<int:article_id>")
def api_summarize(article_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
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
    
    conn.execute("UPDATE articles SET summary = ? WHERE id = ?", (summary, article_id))
    conn.commit()
    conn.close()
    return jsonify({"summary": summary, "cached": False, "tier": tier})


@app.route("/api/cluster-summary/<cluster_id>")
def api_cluster_summary(cluster_id: str):
    conn = get_db()
    try:
        row = conn.execute("SELECT summary FROM cluster_summaries WHERE cluster_id = ?", (cluster_id,)).fetchone()
        if row:
            count_row = conn.execute("SELECT COUNT(*) as count FROM articles WHERE cluster_id = ?", (cluster_id,)).fetchone()
            return jsonify({
                "summary": row["summary"],
                "source_count": count_row["count"] if count_row else 0,
                "cached": True,
                "tier": "db_cache"
            })

        rows = conn.execute("SELECT * FROM articles WHERE cluster_id = ? ORDER BY created_at ASC LIMIT 10", (cluster_id,)).fetchall()
        if not rows:
            return jsonify({"error": "Cluster not found"}), 404

        articles = [dict(r) for r in rows]
        headlines = "\n".join(f"- [{a['source']}]: {a['title']}" for a in articles)

        try:
            raw_res = _call_gemini(f"Наслови:\n{headlines}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True)
            if not raw_res:
                return jsonify({"error": "AI сервисот е недостапен."}), 503
            
            summary = clean_json_response(raw_res)
            now = datetime.datetime.now().isoformat()
            
            conn.execute(
                "INSERT OR REPLACE INTO cluster_summaries (cluster_id, summary, created_at) VALUES (?, ?, ?)",
                (cluster_id, summary, now)
            )
            conn.commit()
            return jsonify({"summary": summary})
            
        except Exception as e:
            if '429' in str(e) or 'ResourceExhausted' in str(e):
                return jsonify({"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."})
            return jsonify({"error": "AI сервисот е недостапен."}), 503
    finally:
        conn.close()


@app.route("/api/analyze/<cluster_id>")
def api_analyze(cluster_id: str):
    if cluster_id in _analysis_cache:
        return jsonify({"analysis": _analysis_cache[cluster_id], "cached": True})

    try:
        conn = get_db()
        rows = conn.execute("SELECT * FROM articles WHERE cluster_id = ? ORDER BY created_at ASC LIMIT 10", (cluster_id,)).fetchall()
        conn.close()
    except Exception:
        log.error("[analyze] DB error:\n" + traceback.format_exc())
        return jsonify({"error": "Database error"}), 500

    if not rows:
        return jsonify({"error": "Cluster not found"}), 404

    articles = [dict(r) for r in rows]
    import re as _re
    lines = []
    for a in articles:
        line = f"- [{a['source']}]: {a['title']}"
        desc = (a.get('description') or '').strip()
        if desc:
            desc = _re.sub(r'<[^>]+>', '', desc)[:250].strip()
            line += f"\n  Опис: {desc}"
        lines.append(line)
    content = "\n".join(lines)

    if not content.strip():
        return jsonify({"error": "Нема доволно содржина за анализа."}), 422

    try:
        analysis = _call_gemini(f"Статии:\n{content}", ANALYSIS_SYSTEM_PROMPT, timeout=40)
    except Exception:
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    if not analysis:
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    analysis = clean_json_response(analysis)
    _analysis_cache[cluster_id] = analysis
    return jsonify({"analysis": analysis, "cached": False})


@app.route("/api/click/<int:article_id>", methods=["POST"])
def api_click(article_id: int):
    try:
        conn = get_db()
        conn.execute("UPDATE articles SET clicks = COALESCE(clicks,0) + 1 WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/popular")
def api_popular():
    cached = cached_response("popular", ttl=120)
    if cached: return jsonify(cached)
    
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM articles
        WHERE created_at >= datetime('now', '-7 days')
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
    set_cache("popular", result)
    return jsonify(result)

@app.route("/api/top10")
def api_top10():
    cached = cached_response("top10", ttl=60)
    if cached: return jsonify(cached)
    
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles WHERE created_at >= datetime('now', '-1 day') ORDER BY created_at DESC LIMIT 500").fetchall()
    
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
    set_cache("top10", result)
    return jsonify(result)

@app.route("/api/timeboxed")
def api_timeboxed():
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles WHERE created_at >= datetime('now', '-1 day') ORDER BY created_at DESC LIMIT 500").fetchall()
    conn.close()

    def window_for(ts):
        try:
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

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2: return jsonify([])
    
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles WHERE title LIKE ? OR source LIKE ? ORDER BY created_at DESC LIMIT 200", (f"%{q}%", f"%{q}%")).fetchall()
    conn.close()
    
    clusters = defaultdict(list)
    for r in rows:
        clusters[r["cluster_id"]].append(dict(r))
        
    ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
    sorted_clusters = sorted(ranked, key=score_cluster, reverse=True)
    result = []
    for arts in sorted_clusters:
        s = score_cluster(arts)
        result.append({
            "articles":    arts,
            "score":       round(s, 3),
            "cluster_id":  arts[0]["cluster_id"] if arts else None,
            "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
        })
    return jsonify(result)

@app.route("/api/archive")
def api_archive():
    date_str = request.args.get("date", "")
    page = request.args.get("page", 0, type=int)
    page_size = request.args.get("page_size", 50, type=int)
    page_size = min(page_size, 100)

    if not date_str:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    try:
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM articles WHERE date(created_at) = ?", (date_str,)).fetchone()[0]
        sources = conn.execute("SELECT COUNT(DISTINCT source) FROM articles WHERE date(created_at) = ?", (date_str,)).fetchone()[0]
        categories = conn.execute("SELECT COUNT(DISTINCT category) FROM articles WHERE date(created_at) = ?", (date_str,)).fetchone()[0]

        offset = page * page_size
        rows = conn.execute("SELECT * FROM articles WHERE date(created_at) = ? ORDER BY created_at DESC LIMIT ? OFFSET ?", (date_str, page_size, offset)).fetchall()
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

@app.route("/api/stats/full")
def api_stats_full():
    try:
        conn = get_db()
        total      = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        by_cat     = conn.execute("SELECT category, COUNT(*) n FROM articles GROUP BY category ORDER BY n DESC").fetchall()
        by_source  = conn.execute("SELECT source, COUNT(*) n FROM articles GROUP BY source ORDER BY n DESC").fetchall()
        recent_24h = conn.execute("SELECT COUNT(*) FROM articles WHERE created_at >= datetime('now','-1 day')").fetchone()[0]
        recent_7d  = conn.execute("SELECT COUNT(*) FROM articles WHERE created_at >= datetime('now','-7 days')").fetchone()[0]
        summarized = conn.execute("SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''").fetchone()[0]
        top_clicks = conn.execute("SELECT title, source, clicks, link FROM articles WHERE clicks > 0 ORDER BY clicks DESC LIMIT 10").fetchall()
        oldest     = conn.execute("SELECT MIN(created_at) FROM articles").fetchone()[0]
        newest     = conn.execute("SELECT MAX(created_at) FROM articles").fetchone()[0]
        conn.close()

        db_size = os.path.getsize(DB_PATH) / (1024*1024)
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
            "by_category": [{"cat": r[0] or "Македонија", "n": r[1]} for r in by_cat],
            "by_source": [{"source": r[0], "n": r[1]} for r in by_source],
            "top_clicked": [{"title": r[0][:70], "source": r[1], "clicks": r[2], "link": r[3]} for r in top_clicks],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat_cluster", methods=["POST"])
def api_chat_cluster():
    data = request.json
    cluster_id = data.get("cluster_id")
    query = data.get("query")
    if not cluster_id or not query: return jsonify({"error": "Missing cluster_id or query"}), 400

    conn = get_db()
    rows = conn.execute("SELECT source, title, description FROM articles WHERE cluster_id = ?", (cluster_id,)).fetchall()
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
        log.error(f"AI Chat error: {e}")
        return jsonify({"error": "AI сервисот е моментално преоптоварен."}), 503

# =====================================================================
# VIEWS & STATICS
# =====================================================================

@app.route("/")
def index():
    return render_template("index.html", year=datetime.datetime.now().year)

@app.route("/izvori")
def izvori_page():
    return render_template("izvori.html", year=datetime.datetime.now().year)

@app.route("/stats")
def stats_page():
    return render_template("stats.html", year=datetime.datetime.now().year)

@app.route("/arhiva")
def archive_page():
    return render_template("archive.html", year=datetime.datetime.now().year)

@app.route("/about")
def about_page():
    return render_template("about.html", year=datetime.datetime.now().year)

@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html", year=datetime.datetime.now().year)

@app.route("/contact")
def contact_page():
    return render_template("contact.html", year=datetime.datetime.now().year)

@app.route("/cluster/<cluster_id>")
def cluster_page(cluster_id: str):
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles WHERE cluster_id = ? ORDER BY created_at DESC", (cluster_id,)).fetchall()
    
    # Fetch synthesis from DB cache if available
    synthesis = None
    s_row = conn.execute("SELECT summary FROM cluster_summaries WHERE cluster_id = ?", (cluster_id,)).fetchone()
    if s_row:
        synthesis = s_row["summary"]
    conn.close()
    
    if not rows: return "Кластерот не постои.", 404
    
    articles = rank_articles_in_cluster([dict(r) for r in rows])
    return render_template("cluster.html", cluster_id=cluster_id, articles=articles, synthesis=synthesis, year=datetime.datetime.now().year)

@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

@app.route("/sw.js")
def service_worker():
    resp = app.send_static_file("sw.js") if os.path.exists(os.path.join(app.static_folder, "sw.js")) else Response("", mimetype="application/javascript")
    if os.path.exists("sw.js") and not os.path.exists(os.path.join(app.static_folder, "sw.js")):
         from flask import send_from_directory
         resp = send_from_directory(os.path.dirname(os.path.abspath(__file__)), "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/robots.txt")
def robots_txt():
    content = "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /proxy\n\nSitemap: https://presek.live/sitemap.xml\n"
    return Response(content, mimetype="text/plain")

@app.route("/sitemap.xml")
def sitemap_xml():
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    urls = [
        ("https://presek.live/", now, "always", "1.0"),
        ("https://presek.live/izvori", now, "monthly", "0.5"),
        ("https://presek.live/stats", now, "daily", "0.4"),
        ("https://presek.live/arhiva", now, "daily", "0.6"),
        ("https://presek.live/about", now, "monthly", "0.3"),
        ("https://presek.live/privacy", now, "monthly", "0.2"),
        ("https://presek.live/contact", now, "monthly", "0.2"),
    ]
    try:
        conn = get_db()
        clusters = conn.execute("SELECT cluster_id, MAX(created_at) as latest FROM articles WHERE created_at >= datetime('now', '-14 days') GROUP BY cluster_id ORDER BY latest DESC").fetchall()
        conn.close()
        for c in clusters:
            lastmod = c['latest'][:10] if c['latest'] else now
            urls.append((f"https://presek.live/cluster/{c['cluster_id']}", lastmod, "daily", "0.7"))
    except Exception as e:
        log.error(f"Sitemap DB error: {e}")

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, lastmod, freq, priority in urls:
        xml += f'  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>{freq}</changefreq>\n    <priority>{priority}</priority>\n  </url>\n'
    xml += '</urlset>'
    return Response(xml, mimetype="application/xml")

@app.route("/favicon.ico")
def favicon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#8b1a1a"/><text x="16" y="23" font-family="serif" font-size="20" font-weight="bold" text-anchor="middle" fill="#f2ead8">П</text></svg>"""
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

@app.route("/proxy")
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

@app.route("/og-image.svg")
def og_image():
    conn = get_db()
    count = conn.execute("SELECT COUNT(DISTINCT source) FROM articles WHERE created_at >= datetime('now', '-1 day')").fetchone()[0]
    conn.close()
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#151310"/><rect x="0" y="0" width="1200" height="6" fill="#c04040"/><text x="600" y="260" font-family="Georgia,serif" font-size="96" font-weight="bold" text-anchor="middle" fill="#c9a030">ПРЕСЕК</text><text x="600" y="340" font-family="sans-serif" font-size="32" text-anchor="middle" fill="#d4c8a8">Македонски агрегатор на вести</text><text x="600" y="420" font-family="sans-serif" font-size="24" text-anchor="middle" fill="#8a7c62">{count}+ извори · AI резимеа · Ажурирано на 5 мин</text><rect x="0" y="624" width="1200" height="6" fill="#c04040"/></svg>"""
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})

if __name__ == "__main__":
    init_db()
    threading.Thread(target=ingest_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
