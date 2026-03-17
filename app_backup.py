from __future__ import annotations
import datetime, os, sqlite3, threading, time, feedparser, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from collections import defaultdict

import health
import trending
import clustering
from categories import detect_category
from notifier import BreakingNewsNotifier
import digest as digest_module

app = Flask(__name__)
CORS(app)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "presek.db"))
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "presek-mk-vesti")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

REFRESH_INTERVAL = 900
FEED_LIMIT = 10
CLUSTER_LOOKBACK = 500  # increased from 200 — handles 36 sources × 10 entries per refresh

# In-memory cache for cluster-wide AI summaries (persists until process restart)
_cluster_summary_cache: dict[str, str] = {}

RSS_FEEDS = [
    # ── Original 10 ──────────────────────────────────────────────
    ("Sloboden Pecat",  "https://slobodenpecat.mk/feed/"),
    ("Kanal 5",         "https://kanal5.com.mk/feed/"),
    ("MIA",             "https://mia.mk/mk/rss"),
    ("Sitel",           "https://sitel.com.mk/rss.xml"),
    ("Telma",           "https://telma.com.mk/feed/"),
    ("Kurir",           "https://kurir.mk/feed/"),
    ("Republika",       "https://republika.mk/feed/"),
    ("Fokus",           "https://fokus.mk/feed/"),
    ("Nezavisen",       "https://nezavisen.mk/feed/"),
    ("Faktor",          "https://faktor.mk/rss"),
    # ── Batch 2 ──────────────────────────────────────────────────
    ("Vecer",           "https://vecer.mk/feed/"),
    ("Meta",            "https://meta.mk/feed/"),
    ("360 Stepeni",     "https://360stepeni.mk/feed/"),
    ("Makfax",          "https://makfax.com.mk/feed/"),
    ("Nova Makedonija", "https://novamakedonija.com.mk/feed/"),
    ("Infomax",         "https://infomax.mk/feed/"),
    # ── Batch 3 ──────────────────────────────────────────────────
    ("Press24",         "https://press24.mk/feed/"),
    ("Skopje1",         "https://skopje1.mk/feed/"),
    ("Plusinfo",        "https://plusinfo.mk/feed/"),
    ("Lokalno",         "https://lokalno.mk/feed/"),
    ("4News",           "https://4news.mk/feed/"),
    ("Makpress",        "https://makpress.mk/feed/"),
    ("Vistinomer",      "https://vistinomer.mk/feed/"),
    ("Portalb",         "https://portalb.mk/feed/"),
    ("Lider",           "https://lider.mk/feed/"),
    ("MKD",             "https://mkd.mk/feed/"),
    ("NetPress",        "https://netpress.com.mk/feed/"),
    ("Akademik",        "https://akademik.mk/feed/"),
    ("Skopje Info",     "https://skopjeinfo.mk/feed/"),
    ("Prizma",          "https://prizma.mk/feed/"),
    ("Expres",          "https://expres.mk/feed/"),
    ("Tetovo Info",     "https://tetovoinfo.mk/feed/"),
    ("Koha",            "https://koha.mk/feed/"),
    ("A1on",            "https://a1on.mk/feed/"),
    ("SportSport",      "https://sportsport.mk/feed/"),
    ("Strumica Info",   "https://strumicainfo.mk/feed/"),
    # ── Batch 4 — sourced from time.mk index ─────────────────────
    ("24 Вести",        "https://24.mk/feed/"),
    ("TV21",            "https://tv21.mk/feed/"),
    ("Слободна Европа", "https://www.slobodnaevropa.mk/api/zryoyqpmou"),
    ("Deutsche Welle",  "https://feeds.dw.com/rss/rss-mac-all"),
    ("Журнал",          "https://zurnal.mk/feed/"),
    ("Civil Media",     "https://civil.mk/feed/"),
    ("Радио МОФ",       "https://radiomof.mk/feed/"),
    ("Сакам да кажам",  "https://sdk.mk/feed/"),
    ("Бизнис Вести",    "https://biznisvesti.mk/feed/"),
]

# ── Source credibility weights (PageRank-style) ──────────────────
# Scale: 1.0 = baseline, higher = more authoritative
# Major national outlets score higher; aggregators/local portals lower
SOURCE_CREDIBILITY = {
    "MIA":              2.0,  # state news agency — primary source
    "MRT":              1.8,  # national public broadcaster
    "Sitel":            1.7,  # major national TV
    "Kanal 5":          1.7,  # major national TV
    "Telma":            1.6,  # major national TV
    "Alfa TV":          1.5,
    "Sloboden Pecat":   1.5,  # established print/online
    "Nova Makedonija":  1.5,  # oldest daily newspaper
    "Republika":        1.4,
    "Makfax":           1.4,  # established wire service
    "Fokus":            1.3,
    "Nezavisen":        1.3,
    "Kurir":            1.2,
    "Faktor":           1.2,
    "Vecer":            1.2,
    "Meta":             1.2,
    "360 Stepeni":      1.1,
    "Infomax":          1.1,
    "Lider":            1.1,
    "Vistinomer":       1.2,  # fact-checking outlet — boost
    "Birn":             1.3,  # regional investigative journalism
    "Akademik":         1.1,
    "NetPress":         1.0,
    "Portalb":          1.0,
    "MKD":              1.0,
    "Press24":          0.9,
    "Skopje1":          0.9,
    "Plusinfo":          0.9,
    "Lokalno":          0.9,
    "4News":            0.9,
    "Makpress":         0.9,
    "Skopje Info":      0.8,
    "Prizma":           0.8,
    "Expres":           0.8,
    "Tetovo Info":      0.8,
    "Koha":             0.8,
    "A1on":             0.8,
    "SportSport":       0.8,
    "Strumica Info":    0.8,
    # Batch 4
    "24 Вести":         1.6,  # major national TV
    "TV21":             1.6,  # major national TV
    "Слободна Европа":  1.8,  # RFE/RL — internationally funded, editorially independent
    "Deutsche Welle":   1.7,  # international public broadcaster, MK edition
    "Журнал":           1.2,
    "Civil Media":      1.3,  # independent civil society media
    "Радио МОФ":        1.1,  # youth/independent online radio
    "Сакам да кажам":   1.1,
    "Бизнис Вести":     1.0,
}
DEFAULT_CREDIBILITY = 0.8  # fallback for unlisted sources

# Breaking news threshold — score above this gets a 🔴 badge in the UI
BREAKING_SCORE_THRESHOLD = 3.0
DB_RETAIN_DAYS = 14  # articles older than this are pruned daily

ntfy = BreakingNewsNotifier(topic=NTFY_TOPIC, threshold=3)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_feed(source, url):
    """Fetch a single RSS feed. Returns list of (title, link, desc, image_url) tuples."""
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "Presek.mk/1.0"})
        entries = []
        for entry in feed.entries[:FEED_LIMIT]:
            title = getattr(entry, "title", "").strip()
            link  = getattr(entry, "link",  "").strip()
            desc  = getattr(entry, "summary", "")
            
            # --- Image Extraction Logic ---
            image_url = ""
            # 1. media:content
            if not image_url and hasattr(entry, 'media_content') and entry.media_content:
                for m in entry.media_content:
                    u = m.get('url', '')
                    if u and any(ext in u.lower() for ext in ['.jpg','.jpeg','.png','.webp','.gif']):
                        image_url = u; break
                if not image_url:
                    image_url = entry.media_content[0].get('url', '')
            # 2. enclosure
            if not image_url and hasattr(entry, 'enclosures') and entry.enclosures:
                for enc in entry.enclosures:
                    if 'image' in enc.get('type','') or any(ext in enc.get('url','').lower() for ext in ['.jpg','.jpeg','.png','.webp']):
                        image_url = enc.get('url',''); break
            # 3. links with image type
            if not image_url and hasattr(entry, 'links'):
                for link_obj in entry.links:
                    if 'image' in link_obj.get('type', ''):
                        image_url = link_obj.get('href', ''); break
            # 4. <img> in description HTML
            if not image_url and desc:
                import re as _re
                m = _re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc, _re.IGNORECASE)
                if m:
                    c = m.group(1)
                    if not any(s in c.lower() for s in ['pixel','icon','1x1','logo','gravatar','avatar']):
                        image_url = c
            # 5. media:thumbnail
            if not image_url and hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get('url', '')
            if image_url and (image_url.startswith('data:') or len(image_url) < 10):
                image_url = ""
            
            if title and link:
                entries.append((title, link, desc, image_url))
        return source, entries, None
    except Exception as e:
        return source, [], str(e)


def ingest_feeds():
    """Fetch all RSS feeds in parallel, then write to DB sequentially."""
    conn = get_db()
    recent_rows = conn.execute(
        "SELECT title, cluster_id FROM articles ORDER BY created_at DESC LIMIT ?",
        (CLUSTER_LOOKBACK,)
    ).fetchall()
    recent_articles = [{"title": r["title"], "cluster_id": r["cluster_id"]} for r in recent_rows]

    # ── Phase 1: fetch all feeds in parallel ─────────────────────
    all_entries = []  
    errors = []
    max_workers = min(len(RSS_FEEDS), 20)  
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_feed, s, u): s for s, u in RSS_FEEDS}
        for future in as_completed(futures):
            source, entries, error = future.result()
            if error:
                errors.append(f"{source}: {error}")
                print(f"[ingest error] {source}: {error}")
            else:
                for title, link, desc, image_url in entries:
                    all_entries.append((source, title, link, desc, image_url))

    # ── Phase 2: write to DB sequentially (no lock contention) ───
    new_count = 0
    for source, title, link, desc, image_url in all_entries:
        try:
            if conn.execute("SELECT id FROM articles WHERE link = ?", (link,)).fetchone():
                continue
            category   = detect_category(title, description=desc, source=source)
            cluster_id = clustering.find_or_create_cluster(title, recent_articles)
            now        = datetime.datetime.now().isoformat()
            conn.execute(
                "INSERT INTO articles (title, link, source, category, cluster_id, created_at, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (title, link, source, category, cluster_id, now, image_url)
            )
            recent_articles.insert(0, {"title": title, "cluster_id": cluster_id})
            if len(recent_articles) > CLUSTER_LOOKBACK:
                recent_articles.pop()
            new_count += 1
        except Exception as e:
            print(f"[db error] {source} — {title[:40]}: {e}")

    conn.commit()
    conn.close()
    return new_count, errors


def prune_db():
    """Delete articles older than DB_RETAIN_DAYS and reclaim disk space."""
    try:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=DB_RETAIN_DAYS)).isoformat()
        conn = get_db()
        result = conn.execute("DELETE FROM articles WHERE created_at < ?", (cutoff,))
        deleted = result.rowcount
        conn.execute("VACUUM")
        conn.commit()
        conn.close()
        if deleted:
            print(f"[prune] Deleted {deleted} articles older than {DB_RETAIN_DAYS} days.")
    except Exception as e:
        print(f"[prune] Error: {e}")

_prune_counter = 0
_digest_counter = 0

def ingest_loop():
    while True:
        try:
            print("[ingest] Fetching RSS feeds...")
            new_count, errors = ingest_feeds()
            health.record_refresh(new_count, errors)
            print(f"[ingest] Added {new_count} new articles, {len(errors)} errors.")
            global _prune_counter
            _prune_counter += 1
            if _prune_counter >= 96:
                prune_db()
                _prune_counter = 0
            global _digest_counter
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
                    print(f"[digest] Failed: {_de}")
                _digest_counter = 0
            
            conn = get_db()
            rows = conn.execute("SELECT * FROM articles ORDER BY created_at DESC LIMIT 500").fetchall()
            conn.close()
            cmap = defaultdict(list)
            for r in rows: cmap[r["cluster_id"]].append(dict(r))
            ntfy.check_and_notify([{"cluster_id": cid, "articles": arts} for cid, arts in cmap.items()])
            
        except Exception as e:
            print(f"[error] Ingest loop failed: {e}")
        time.sleep(REFRESH_INTERVAL)

health.register_health_routes(app, DB_PATH)
trending.register_trending_route(app, DB_PATH)

def score_cluster(arts):
    """
    PageRank-style cluster importance score.
    Combines:
      - Source count (breadth of coverage)
      - Credibility-weighted source score
      - Recency (decays over 24h)
    """
    import math
    now = datetime.datetime.now()

    # Credibility score — sum of weights of unique sources
    unique_sources = {a["source"] for a in arts}
    cred_score = sum(
        SOURCE_CREDIBILITY.get(s, DEFAULT_CREDIBILITY)
        for s in unique_sources
    )

    # Recency score — exponential decay, half-life = 6 hours
    try:
        latest = datetime.datetime.fromisoformat(arts[0]["created_at"].replace("+00:00", ""))
        hours_old = (now - latest).total_seconds() / 3600
    except Exception:
        hours_old = 24
    recency = math.exp(-0.115 * hours_old)  # e^(-ln2/6 * h) ≈ halves every 6h

    # Source count bonus (logarithmic — diminishing returns)
    breadth = math.log1p(len(arts))

    return cred_score * recency * breadth


def rank_articles_in_cluster(arts):
    """Within a cluster, put the most credible source first."""
    return sorted(
        arts,
        key=lambda a: SOURCE_CREDIBILITY.get(a["source"], DEFAULT_CREDIBILITY),
        reverse=True
    )


@app.route("/api/news")
def api_news():
    limit = request.args.get("limit", 250, type=int)
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()

    clusters = defaultdict(list)
    for r in rows:
        clusters[r['cluster_id']].append(dict(r))

    # Within each cluster: most credible source first
    ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]

    # Across clusters: PageRank score determines feed order
    sorted_clusters = sorted(ranked_clusters, key=score_cluster, reverse=True)

    # Return structured objects so frontend can use score for breaking badge
    result = []
    for arts in sorted_clusters:
        s = score_cluster(arts)
        result.append({
            "articles": arts,
            "score": round(s, 3),
            "cluster_id": arts[0]["cluster_id"] if arts else None,
            "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
        })

    return jsonify(result)


@app.route("/api/scores")
def api_scores():
    """Debug endpoint — shows PageRank scores for current top clusters."""
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
    return jsonify(result[:20])


SUMMARY_SYSTEM_PROMPT = (
    "Ти си уредник на македонска новинска агенција. "
    "Даден ти е наслов на вест. Одговори САМО во овој формат (без дополнителен текст):\n"
    "Линија 1: Сентимент (🟢 позитивно / 🔴 негативно / ⚪ неутрално)\n"
    "Линија 2-3: Резиме во 2 реченици на македонски.\n"
    "Линија 4: Тагови — 3 до 5 клучни зборови со # (пр. #Скопје #Влада)"
)

SYNTHESIS_SYSTEM_PROMPT = (
    "Ти си уредник на македонска новинска агенција. "
    "Дадени ти се повеќе наслови од различни извори за иста приказна. "
    "Одговори САМО во овој формат (без дополнителен текст):\n"
    "Линија 1: Сентимент (🟢 позитивно / 🔴 негативно / ⚪ неутрално)\n"
    "Линија 2-4: Синтеза во 2-3 реченици — опфати различни перспективи и кажи "
    "што сите извори заедно кажуваат, вклучувајќи и спротивставени гледишта.\n"
    "Линија 5: Тагови — 3 до 5 клучни зборови со # (пр. #Скопје #Влада)"
)

def call_openrouter(prompt_text: str, system_prompt: str, timeout: int = 25) -> str:
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    resp = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "qwen/qwen-2.5-72b-instruct:free",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt_text}
            ],
            "max_tokens": 500,
        },
        timeout=timeout
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


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

    summary = None
    tier = None

    # Primary: Gemini
    if GOOGLE_API_KEY:
        try:
            payload = {
                "system_instruction": {"parts": [{"text": SUMMARY_SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": row["title"]}]}]
            }
            resp = requests.post(f"{GEMINI_URL}?key={GOOGLE_API_KEY}", json=payload, timeout=20)
            resp.raise_for_status()
            summary = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            tier = "gemini"
        except Exception as e:
            print(f"[summarize] Gemini failed for {article_id}: {e}")

    # Fallback: OpenRouter
    if not summary and OPENROUTER_API_KEY:
        try:
            summary = call_openrouter(row["title"], SUMMARY_SYSTEM_PROMPT)
            tier = "openrouter"
        except Exception as e:
            print(f"[summarize] OpenRouter failed for {article_id}: {e}")

    if not summary:
        conn.close()
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    conn.execute("UPDATE articles SET summary = ? WHERE id = ?", (summary, article_id))
    conn.commit()
    conn.close()
    return jsonify({"summary": summary, "cached": False, "tier": tier})


@app.route("/api/cluster-summary/<cluster_id>")
def api_cluster_summary(cluster_id: str):
    """
    Cluster-wide AI synthesis — feeds all articles in a cluster to Gemini
    and returns a cross-source summary with multiple perspectives.
    Results are cached in memory for the lifetime of the process.
    """
    # Return cached result if available
    if cluster_id in _cluster_summary_cache:
        return jsonify({"summary": _cluster_summary_cache[cluster_id], "cached": True})

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE cluster_id = ? ORDER BY created_at ASC LIMIT 10",
        (cluster_id,)
    ).fetchall()
    conn.close()

    if not rows:
        return jsonify({"error": "Cluster not found"}), 404

    articles = [dict(r) for r in rows]
    headlines = "\n".join(
        f"- [{a['source']}]: {a['title']}"
        for a in articles
    )

    summary = None
    tier = None

    # Primary: Gemini
    if GOOGLE_API_KEY:
        try:
            payload = {
                "system_instruction": {"parts": [{"text": SYNTHESIS_SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": f"Наслови:\n{headlines}"}]}]
            }
            resp = requests.post(f"{GEMINI_URL}?key={GOOGLE_API_KEY}", json=payload, timeout=30)
            resp.raise_for_status()
            summary = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            tier = "gemini"
        except Exception as e:
            print(f"[cluster-summary] Gemini failed for {cluster_id}: {e}")

    # Fallback: OpenRouter
    if not summary and OPENROUTER_API_KEY:
        try:
            summary = call_openrouter(f"Наслови:\n{headlines}", SYNTHESIS_SYSTEM_PROMPT, timeout=30)
            tier = "openrouter"
        except Exception as e:
            print(f"[cluster-summary] OpenRouter failed for {cluster_id}: {e}")

    if not summary:
        return jsonify({"error": "AI сервисот е недостапен."}), 503

    _cluster_summary_cache[cluster_id] = summary
    return jsonify({"summary": summary, "source_count": len(articles), "cached": False, "tier": tier})




@app.route("/api/click/<int:article_id>", methods=["POST"])
def api_click(article_id: int):
    """Increment click counter for an article."""
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
    """Return most-clicked clusters in the last 7 days."""
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
    for arts in sorted_clusters[:20]:
        result.append({
            "articles":    arts,
            "score":       round(score_cluster(arts), 3),
            "cluster_id":  arts[0]["cluster_id"],
            "total_clicks": sum(a.get("clicks",0) for a in arts),
            "is_breaking": False,
        })
    return jsonify(result)

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE title LIKE ? OR source LIKE ? ORDER BY created_at DESC LIMIT 200",
        (f"%{q}%", f"%{q}%")
    ).fetchall()
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


@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

@app.route("/sw.js")
def service_worker():
    from flask import Response, send_from_directory
    resp = send_from_directory(
        os.path.dirname(os.path.abspath(__file__)), "sw.js"
    )
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/")
def index():
    return render_template("index.html", year=__import__('datetime').datetime.now().year)

if __name__ == "__main__":
    conn = get_db()
    # Create table if new install
    conn.execute("""CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, link TEXT UNIQUE, source TEXT,
        category TEXT, summary TEXT, cluster_id TEXT,
        created_at TEXT, image_url TEXT
    )""")
    # Migrate existing DB — add image_url if not present
    cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
    if "image_url" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT DEFAULT ''")
        print("[db] Migrated: added image_url column")
    if "clicks" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN clicks INTEGER DEFAULT 0")
        print("[db] Migrated: added clicks column")
    conn.commit()
    conn.close()

    threading.Thread(target=ingest_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
