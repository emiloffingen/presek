from flask import Blueprint, render_template, Response, request, current_app, send_from_directory
import datetime
import os
from database import get_db
from utils import rank_articles_in_cluster

views_bp = Blueprint('views', __name__)

@views_bp.route("/")
def index():
    return render_template("index.html", year=datetime.datetime.now().year)

@views_bp.route("/izvori")
def izvori_page():
    return render_template("izvori.html", year=datetime.datetime.now().year)

@views_bp.route("/stats")
def stats_page():
    return render_template("stats.html", year=datetime.datetime.now().year)

@views_bp.route("/arhiva")
def archive_page():
    return render_template("archive.html", year=datetime.datetime.now().year)

@views_bp.route("/briefing")
def briefing_page():
    return render_template("briefing.html", year=datetime.datetime.now().year)

@views_bp.route("/about")
def about_page():
    return render_template("about.html", year=datetime.datetime.now().year)

@views_bp.route("/privacy")
def privacy_page():
    return render_template("privacy.html", year=datetime.datetime.now().year)

@views_bp.route("/contact")
def contact_page():
    return render_template("contact.html", year=datetime.datetime.now().year)

@views_bp.route("/cluster/<cluster_id>")
def cluster_page(cluster_id: str):
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", (cluster_id,)).fetchall()
    
    # Fetch synthesis and tags
    synthesis = None
    tags = []
    
    s_row = conn.execute("SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,)).fetchone()
    if s_row:
        synthesis = s_row["summary"]
        
    m_row = conn.execute("SELECT tags FROM cluster_metadata WHERE cluster_id = %s", (cluster_id,)).fetchone()
    if m_row:
        tags = m_row["tags"]
        
    # Find Related Clusters (share at least one tag, last 48h)
    related_clusters = []
    if tags:
        related_rows = conn.execute("""
            SELECT m.cluster_id, m.tags, ANY_VALUE(a.title) as title, ANY_VALUE(a.image_url) as image_url, COUNT(*) as shared_count
            FROM cluster_metadata m
            JOIN articles a ON m.cluster_id = a.cluster_id
            WHERE m.cluster_id != %s 
              AND a.created_at >= NOW() - INTERVAL '48 hours'
              AND m.tags && %s
            GROUP BY m.cluster_id, m.tags
            ORDER BY shared_count DESC, MAX(a.created_at) DESC
            LIMIT 4
        """, (cluster_id, tags)).fetchall()
        related_clusters = [dict(r) for r in related_rows]

    conn.close()
    
    if not rows: return "Кластерот не постои.", 404
    
    articles = rank_articles_in_cluster([dict(r) for r in rows])
    
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
        "image": articles[0]["image_url"],
        "url": f"https://presek.mk/cluster/{cluster_id}"
    }

    return render_template("cluster.html", cluster_id=cluster_id, articles=articles, synthesis=synthesis, meta=meta, tags=tags, related_clusters=related_clusters, year=datetime.datetime.now().year)

@views_bp.route("/manifest.json")
def manifest():
    return current_app.send_static_file("manifest.json")

@views_bp.route("/sw.js")
def service_worker():
    static_folder = current_app.static_folder
    resp = current_app.send_static_file("sw.js") if os.path.exists(os.path.join(static_folder, "sw.js")) else Response("", mimetype="application/javascript")
    if os.path.exists("sw.js") and not os.path.exists(os.path.join(static_folder, "sw.js")):
         resp = send_from_directory(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@views_bp.route("/robots.txt")
def robots_txt():
    content = "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /proxy\n\nSitemap: https://presek.mk/sitemap.xml\n"
    return Response(content, mimetype="text/plain")

@views_bp.route("/sitemap.xml")
def sitemap_xml():
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    urls = [
        ("https://presek.mk/", now, "always", "1.0"),
        ("https://presek.mk/izvori", now, "monthly", "0.5"),
        ("https://presek.mk/stats", now, "daily", "0.4"),
        ("https://presek.mk/arhiva", now, "daily", "0.6"),
        ("https://presek.mk/about", now, "monthly", "0.3"),
        ("https://presek.mk/privacy", now, "monthly", "0.2"),
        ("https://presek.mk/contact", now, "monthly", "0.2"),
    ]
    try:
        conn = get_db()
        clusters = conn.execute("SELECT cluster_id, MAX(created_at) as latest FROM articles WHERE created_at >= NOW() - INTERVAL '14 days' GROUP BY cluster_id ORDER BY latest DESC").fetchall()
        conn.close()
        for c in clusters:
            lastmod = c['latest'].strftime("%Y-%m-%d") if isinstance(c['latest'], datetime.datetime) else (str(c['latest'])[:10] if c['latest'] else now)
            urls.append((f"https://presek.mk/cluster/{c['cluster_id']}", lastmod, "daily", "0.7"))
    except Exception as e:
        pass

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, lastmod, freq, priority in urls:
        xml += f'  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>{freq}</changefreq>\n    <priority>{priority}</priority>\n  </url>\n'
    xml += '</urlset>'
    return Response(xml, mimetype="application/xml")

@views_bp.route("/favicon.ico")
def favicon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#8b1a1a"/><text x="16" y="23" font-family="serif" font-size="20" font-weight="bold" text-anchor="middle" fill="#f2ead8">П</text></svg>"""
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

@views_bp.route("/og-image.svg")
def og_image():
    conn = get_db()
    count = conn.execute("SELECT COUNT(DISTINCT source) FROM articles WHERE created_at >= NOW() - INTERVAL '1 day'").fetchone()[0]
    conn.close()
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#151310"/><rect x="0" y="0" width="1200" height="6" fill="#c04040"/><text x="600" y="260" font-family="Georgia,serif" font-size="96" font-weight="bold" text-anchor="middle" fill="#c9a030">ПРЕСЕК</text><text x="600" y="340" font-family="sans-serif" font-size="32" text-anchor="middle" fill="#d4c8a8">Македонски агрегатор на вести</text><text x="600" y="420" font-family="sans-serif" font-size="24" text-anchor="middle" fill="#8a7c62">{count}+ извори · AI резимеа · Ажурирано на 5 мин</text><rect x="0" y="624" width="1200" height="6" fill="#c04040"/></svg>"""
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})
