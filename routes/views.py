from flask import Blueprint, render_template, current_app, request, Response, redirect
from database import db_manager as db, get_db
from utils import score_cluster, is_balanced, cached_response, set_cache, rank_articles_in_cluster, calculate_reading_time
from config import BREAKING_SCORE_THRESHOLD, SOURCE_CATEGORIES, DEFAULT_SOURCE_CATEGORY
from collections import defaultdict
import datetime
import math
import logging
import re
from urllib.parse import quote, urljoin

views_bp = Blueprint('views', __name__)

LEGACY_ROUTE_REDIRECTS = {
    "/": "/",
    "/about": "/about",
    "/arhiva": "/archive",
    "/briefing": "/briefing",
    "/contact": "/about",
    "/izvori": "/izvori",
    "/privacy": "/privacy",
    "/saved": "/",
    "/stats": "/stats",
    "/vesti": "/",
}


def normalize_perspectives(raw_perspectives):
    if not isinstance(raw_perspectives, list):
        return []

    normalized = []
    for item in raw_perspectives:
        if isinstance(item, dict):
            angle = (
                item.get("angle")
                or item.get("label")
                or item.get("title")
                or item.get("name")
                or ""
            )
            content = (
                item.get("content")
                or item.get("text")
                or item.get("description")
                or ""
            )
        elif isinstance(item, str):
            angle = ""
            content = item
        else:
            continue

        angle = str(angle).strip()
        content = str(content).strip()
        if not angle and not content:
            continue

        normalized.append({
            "angle": angle or "Перспектива",
            "content": content,
        })

    return normalized


def _request_is_local() -> bool:
    host = (request.host or "").split(":", 1)[0].lower()
    return host in {"127.0.0.1", "localhost"}


def _public_site_path_for_request(path: str) -> str | None:
    if path.startswith("/cluster/"):
        return path

    if path.startswith("/izvor/"):
        source_name = path.rsplit("/", 1)[-1].strip()
        if not source_name:
            return "/izvori"
        return f"/izvori?source={quote(source_name)}"

    return LEGACY_ROUTE_REDIRECTS.get(path)


def legacy_frontend_redirect(path: str):
    if _request_is_local():
        return None

    enabled = current_app.config.get("REDIRECT_LEGACY_FRONTEND", True)
    if not enabled:
        return None

    public_path = _public_site_path_for_request(path)
    if not public_path:
        return None

    target = urljoin(current_app.config.get("PUBLIC_SITE_URL", "https://presek.live"), public_path)
    return redirect(target, code=302)


@views_bp.before_request
def redirect_legacy_frontend_routes():
    if request.method not in {"GET", "HEAD"}:
        return None

    if not _public_site_path_for_request(request.path):
        return None

    return legacy_frontend_redirect(request.path)

@views_bp.route("/")
def index():
    # SSR Optimization: Fetch first fold of news (10 clusters)
    try:
        cached = cached_response("ssr:index:top_clusters", ttl=60)
        if cached:
            top_clusters = cached
        else:
            # Get latest MK news
            rows = db.get_articles_by_country("🇲🇰")
            clusters = defaultdict(list)
            for r in rows:
                clusters[r['cluster_id']].append(r)
                
            ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
            ranked.sort(key=score_cluster, reverse=True)
            
            top_clusters = []
            
            # Fetch representative images
            cid_list = [arts[0]["cluster_id"] for arts in ranked[:10]]
            metadata_rows = db.execute(
                "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
                (cid_list,)
            )
            rep_images = {r['cluster_id']: r['representative_image'] for r in metadata_rows}

            # We only need the first 10 for Instant Paint
            for arts in ranked[:10]:
                s = score_cluster(arts)
                cid = arts[0]["cluster_id"]
                top_clusters.append({
                    "cluster_id": cid,
                    "articles": arts,
                    "representative_image": rep_images.get(cid),
                    "score": round(s, 3),
                    "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                    "has_balanced": is_balanced(arts)
                })
            set_cache("ssr:index:top_clusters", top_clusters, ttl=60)
    except Exception as e:
        current_app.logger.error(f"SSR Error: {e}")
        top_clusters = []

    # Fetch trending for SSR
    try:
        from trending import get_trending
        trending = get_trending(hours=6, limit=10)
    except Exception as e:
        current_app.logger.warning(f"Trending SSR Error: {e}")
        trending = []

    return render_template("index.html", 
                           initial_clusters=top_clusters,
                           initial_trending=trending,
                           year=datetime.datetime.now().year)

@views_bp.route("/saved")
def saved_page():
    return render_template("index.html", initial_clusters=[], initial_trending=[], year=datetime.datetime.now().year)

@views_bp.route("/izvori")
def izvori_page():
    # Fetch all active sources
    sources = []
    try:
        rows = db.execute("SELECT name, country, category FROM sources WHERE is_active = TRUE ORDER BY name ASC")
        sources = [dict(r) for r in rows]
    except Exception as e:
        current_app.logger.warning(f"Sources SSR Error: {e}")

    # Fetch hot sources (pulse)
    hot_sources = []
    try:
        pulse_rows = db.execute(
            "SELECT source, COUNT(*) as n FROM articles "
            "WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "GROUP BY source ORDER BY n DESC LIMIT 10"
        )
        hot_sources = [r['source'] for r in pulse_rows]
    except Exception as e:
        current_app.logger.warning(f"Pulse SSR Error: {e}")

    # Fetch trending for sidebar
    trending = []
    try:
        from trending import get_trending
        trending = get_trending(hours=6, limit=10)
    except Exception as e:
        current_app.logger.warning(f"Trending SSR Error: {e}")

    return render_template("izvori.html", 
                           sources=sources, 
                           hot_sources=hot_sources,
                           initial_trending=trending,
                           year=datetime.datetime.now().year)

@views_bp.route("/stats")
def stats_page():
    # Fetch stats data (reusing logic from api_stats_full for consistency)
    stats = None
    try:
        from routes.api import api_stats_full
        # We can't call the route function directly easily because of response wrapping,
        # but we can call it and get the JSON. However, let's just use the cached stats if available.
        from utils import cached_response
        stats = cached_response("stats:full", ttl=120)
        if not stats:
            # If not cached, the page will load it via React anyway, 
            # but for a better SSR experience we could trigger a fetch here.
            # For now, let's assume we want to provide at least basic stats if possible.
            pass
    except Exception as e:
        current_app.logger.warning(f"Stats SSR Error: {e}")

    # Fetch trending for sidebar
    trending = []
    try:
        from trending import get_trending
        trending = get_trending(hours=6, limit=10)
    except Exception as e:
        current_app.logger.warning(f"Trending SSR Error: {e}")

    return render_template("stats.html", 
                           initial_stats=stats, 
                           initial_trending=trending,
                           year=datetime.datetime.now().year)

@views_bp.route("/arhiva")
def archive_page():
    # Fetch today's articles for the initial view
    today = datetime.date.today().isoformat()
    archive_data = None
    try:
        from routes.api import api_archive
        # We'll just manually fetch for SSR to avoid complex route calls
        page_size = 50
        rows = db.execute(
            "SELECT id, title, source, link, created_at FROM articles "
            "WHERE created_at::date = %s "
            "ORDER BY created_at DESC LIMIT %s",
            (today, page_size)
        )
        total = db.execute_one(
            "SELECT COUNT(*) FROM articles WHERE created_at::date = %s",
            (today,)
        )["count"]
        sources_count = db.execute_one(
            "SELECT COUNT(DISTINCT source) FROM articles WHERE created_at::date = %s",
            (today,)
        )["count"]
        
        archive_data = {
            "articles": [dict(r) for r in rows],
            "total": total,
            "sources": sources_count,
            "date": today,
            "has_more": total > page_size
        }
    except Exception as e:
        current_app.logger.warning(f"Archive SSR Error: {e}")

    # Fetch trending for sidebar
    trending = []
    try:
        from trending import get_trending
        trending = get_trending(hours=6, limit=10)
    except Exception as e:
        current_app.logger.warning(f"Trending SSR Error: {e}")

    return render_template("archive.html", 
                           initial_archive=archive_data, 
                           initial_trending=trending,
                           year=datetime.datetime.now().year)

@views_bp.route("/briefing")
def briefing_page():
    # Fetch briefing data
    briefing = None
    try:
        row = db.execute_one(
            "SELECT date, content FROM daily_briefings WHERE date = CURRENT_DATE"
        )
        if not row:
            row = db.execute_one(
                "SELECT date, content FROM daily_briefings ORDER BY date DESC LIMIT 1"
            )
        if row:
            briefing = {
                "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"]),
                "content": row["content"] or ""
            }
    except Exception as e:
        current_app.logger.warning(f"Briefing SSR Error: {e}")

    # Fetch trending for sidebar
    trending = []
    try:
        from trending import get_trending
        trending = get_trending(hours=6, limit=10)
    except Exception as e:
        current_app.logger.warning(f"Trending SSR Error: {e}")

    return render_template("briefing.html", 
                           briefing=briefing, 
                           initial_trending=trending,
                           year=datetime.datetime.now().year)

@views_bp.route("/vesti")
def vesti_portal():
    """Portal view showing top clusters from each major category."""
    from collections import defaultdict
    
    categories = ["Македонија", "Економија", "Балкан", "Свет", "Спорт", "Технологија"]
    
    try:
        cached = cached_response("ssr:portal:top_categories", ttl=300)
        if cached:
            portal_data = cached
        else:
            # Single query for all categories, then partition in Python
            all_rows = db.execute(
                "SELECT * FROM articles WHERE category = ANY(%s) AND (country = '🇲🇰' OR country IS NULL OR country = '') ORDER BY created_at DESC LIMIT 1000",
                (categories,)
            )

            # Group by category then cluster_id
            by_cat: dict = {cat: defaultdict(list) for cat in categories}
            for r in all_rows:
                cat = r['category']
                if cat in by_cat:
                    by_cat[cat][r['cluster_id']].append(r)

            # Collect all candidate cluster_ids to batch-fetch rep images
            all_cids = []
            ranked_by_cat: dict = {}
            for cat in categories:
                ranked = [rank_articles_in_cluster(arts) for arts in by_cat[cat].values()]
                ranked.sort(key=score_cluster, reverse=True)
                ranked_by_cat[cat] = ranked[:3]
                all_cids.extend(arts[0]["cluster_id"] for arts in ranked[:3])

            rep_images: dict = {}
            if all_cids:
                metadata_rows = db.execute(
                    "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
                    (all_cids,)
                )
                rep_images = {r['cluster_id']: r['representative_image'] for r in metadata_rows}

            portal_data = {}
            for cat in categories:
                cat_clusters = []
                for arts in ranked_by_cat[cat]:
                    s = score_cluster(arts)
                    cid = arts[0]["cluster_id"]
                    cat_clusters.append({
                        "cluster_id": cid,
                        "articles": arts,
                        "representative_image": rep_images.get(cid),
                        "score": round(s, 3),
                        "is_breaking": s >= BREAKING_SCORE_THRESHOLD
                    })
                portal_data[cat] = cat_clusters
            set_cache("ssr:portal:top_categories", portal_data, ttl=300)
    except Exception as e:
        current_app.logger.error(f"Portal Error: {e}")
        portal_data = {}

    return render_template("portal.html", 
                           portal_data=portal_data,
                           year=datetime.datetime.now().year)

@views_bp.route("/izvor/<source_name>")
def source_page(source_name: str):
    if not source_name or len(source_name) > 100:
        return "Невалиден извор.", 400
    conn = get_db()
    # Fetch recent articles from this source
    rows = conn.execute(
        "SELECT * FROM articles WHERE source = %s ORDER BY created_at DESC LIMIT 50",
        (source_name,)
    ).fetchall()
    
    # Calculate stats for this source
    stats = conn.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN created_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as last_24h,
            (SELECT category FROM articles WHERE source = %s GROUP BY category ORDER BY COUNT(*) DESC LIMIT 1) as top_cat,
            (SELECT topic FROM articles WHERE source = %s GROUP BY topic ORDER BY COUNT(*) DESC LIMIT 1) as top_topic,
            AVG(CASE WHEN summary LIKE '%%🟢%%' THEN 1 WHEN summary LIKE '%%🔴%%' THEN -1 ELSE 0 END) FILTER (WHERE summary IS NOT NULL) as avg_sent
        FROM articles WHERE source = %s
    """, (source_name, source_name, source_name)).fetchone()
    
    # Calculate Frequency (posts per day last 7 days)
    freq_row = conn.execute("""
        SELECT COUNT(*) / 7.0 as daily_avg
        FROM articles 
        WHERE source = %s AND created_at >= NOW() - INTERVAL '7 days'
    """, (source_name,)).fetchone()
    
    conn.close()
    
    if not rows:
        return "Изворот не е пронајден или нема активни објави.", 404
        
    articles = [dict(r) for r in rows]
    # We group them by cluster for better display
    clusters = []
    seen_clusters = set()
    for a in articles:
        if a["cluster_id"] not in seen_clusters:
            clusters.append({
                "cluster_id": a["cluster_id"],
                "articles": [a]
            })
            seen_clusters.add(a["cluster_id"])
        else:
            for c in clusters:
                if c["cluster_id"] == a["cluster_id"]:
                    c["articles"].append(a)
                    break
    
    return render_template("source.html", 
                           source_name=source_name, 
                           clusters=clusters[:20],
                           stats=stats,
                           freq=freq_row["daily_avg"] if freq_row else 0,
                           year=datetime.datetime.now().year)

@views_bp.route("/cluster/<cluster_id>")
def cluster_page(cluster_id: str):
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        return "Невалиден кластер.", 400
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", (cluster_id,)).fetchall()
    
    # Fetch synthesis and tags
    synthesis = None
    perspectives = []
    tags = []
    
    s_row = conn.execute("SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,)).fetchone()
    if s_row:
        synthesis = s_row["summary"]
        perspectives = normalize_perspectives(s_row["perspectives"] if s_row["perspectives"] else [])
        
    m_row = conn.execute("SELECT tags FROM cluster_metadata WHERE cluster_id = %s", (cluster_id,)).fetchone()
    if m_row:
        tags = m_row["tags"]
        
    # Find Related Clusters (share at least one tag, last 48h)
    related_clusters = []
    if tags:
        related_rows = conn.execute("""
            WITH candidates AS (
                SELECT
                    m.cluster_id,
                    m.tags,
                    CARDINALITY(ARRAY(SELECT UNNEST(m.tags) INTERSECT SELECT UNNEST(%s::text[]))) as shared_count,
                    m.updated_at
                FROM cluster_metadata m
                WHERE m.cluster_id != %s
                  AND m.updated_at >= NOW() - INTERVAL '48 hours'
                  AND m.tags && %s::text[]
                ORDER BY shared_count DESC, m.updated_at DESC
                LIMIT 4
            ),
            latest_arts AS (
                SELECT DISTINCT ON (cluster_id) cluster_id, title, image_url
                FROM articles
                WHERE cluster_id IN (SELECT cluster_id FROM candidates)
                ORDER BY cluster_id, created_at DESC
            )
            SELECT c.cluster_id, c.tags, c.shared_count, a.title, a.image_url
            FROM candidates c
            JOIN latest_arts a ON a.cluster_id = c.cluster_id
        """, (tags, cluster_id, tags)).fetchall()
        related_clusters = [dict(r) for r in related_rows]

    conn.close()
    
    if not rows: return "Кластерот не постои.", 404
    
    articles = rank_articles_in_cluster([dict(r) for r in rows])
    
    # Calculate reading times
    total_reading_time = 0
    for a in articles:
        a['reading_time'] = calculate_reading_time(a.get('description', ''))
        total_reading_time += a['reading_time']
    # Average it for the cluster synthesis view
    total_reading_time = max(1, math.ceil(total_reading_time / len(articles))) if articles else 1
    
    # Calculate Source Distribution (Media Plurality)
    dist_map = {}
    for a in articles:
        cat = SOURCE_CATEGORIES.get(a["source"], DEFAULT_SOURCE_CATEGORY)
        dist_map[cat] = dist_map.get(cat, 0) + 1
    
    total_arts = len(articles)
    source_distribution = [
        {"label": cat, "pct": round((count / total_arts) * 100)}
        for cat, count in dist_map.items()
    ]
    source_distribution.sort(key=lambda x: x["pct"], reverse=True)
    
    # SEO Metadata
    description = ""
    if synthesis:
        # Clean synthesis points for meta description
        description = synthesis.replace("•", "").replace("\n", " ").strip()[:200]
    elif articles[0]["description"]:
        description = articles[0]["description"][:200]

    meta = {
        "title": articles[0]["title"],
        "description": description,
        "image": f"https://presek.mk/og/cluster/{cluster_id}.svg",
        "url": f"https://presek.mk/cluster/{cluster_id}"
    }

    return render_template("cluster.html", cluster_id=cluster_id, articles=articles, synthesis=synthesis, perspectives=perspectives, meta=meta, tags=tags, related_clusters=related_clusters, source_distribution=source_distribution, total_reading_time=total_reading_time, year=datetime.datetime.now().year)

@views_bp.route("/about")
def about_page():
    return render_template("about.html", year=datetime.datetime.now().year)

@views_bp.route("/contact")
def contact_page():
    return render_template("contact.html", year=datetime.datetime.now().year)

@views_bp.route("/privacy")
def privacy_page():
    return render_template("privacy.html", year=datetime.datetime.now().year)

@views_bp.route("/robots.txt")
def robots_txt():
    content = "User-agent: *\nDisallow: /api/\nAllow: /\n"
    return Response(content, mimetype="text/plain")

@views_bp.route("/og/cluster/<cluster_id>.svg")
def og_cluster_image(cluster_id: str):
    conn = get_db()
    row = conn.execute("SELECT title FROM articles WHERE cluster_id = %s LIMIT 1", (cluster_id,)).fetchone()
    count_row = conn.execute("SELECT COUNT(*) FROM articles WHERE cluster_id = %s", (cluster_id,)).fetchone()
    conn.close()
    
    title = row["title"] if row else "Вест"
    count = count_row[0] if count_row else 1
    
    # Simple SVG with wrapped title (pseudo-wrapping)
    safe_title = title.replace('"', '&quot;').replace('&', '&amp;')
    if len(safe_title) > 65:
        line1 = safe_title[:65]
        line2 = safe_title[65:130] + ("..." if len(safe_title) > 130 else "")
    else:
        line1 = safe_title
        line2 = ""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#1a1a1a"/>
  <rect width="1200" height="10" y="0" fill="#E63946"/>
  <text x="80" y="120" font-family="serif" font-size="32" font-weight="800" fill="#E63946" text-transform="uppercase" letter-spacing="2">ПРЕСЕК АНАЛИЗА</text>
  <text x="80" y="240" font-family="serif" font-size="56" font-weight="bold" fill="#ffffff">{line1}</text>
  <text x="80" y="320" font-family="serif" font-size="56" font-weight="bold" fill="#ffffff">{line2}</text>
  <text x="80" y="520" font-family="sans-serif" font-size="28" fill="#aaaaaa">{count} извори анализирани во овој кластер</text>
  <text x="1120" y="560" font-family="serif" font-size="48" font-weight="bold" fill="#E63946" text-anchor="end">пресек.мк</text>
</svg>"""
    return Response(svg, mimetype="image/svg+xml")

@views_bp.route("/favicon.ico")
def favicon():
    return current_app.send_static_file("logo.svg")

@views_bp.route("/og-image.svg")
def og_image():
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
    count = row[0] if row else 0
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#1a1a2e"/>
  <text x="600" y="280" font-family="sans-serif" font-size="72" font-weight="bold" fill="#ffffff" text-anchor="middle">Пресек</text>
  <text x="600" y="380" font-family="sans-serif" font-size="36" fill="#aaaaaa" text-anchor="middle">{count} статии индексирани</text>
</svg>"""
    return Response(svg, mimetype="image/svg+xml")
