from __future__ import annotations

import re
from urllib.parse import quote, urljoin

from flask import Blueprint, Response, current_app, redirect, request

from database import get_db

views_bp = Blueprint("views", __name__)

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


def _request_is_local() -> bool:
    host = (request.host or "").split(":", 1)[0].lower()
    return host in {"127.0.0.1", "localhost"}


def _public_site_path_for_request(path: str) -> str | None:
    if path.startswith("/cluster/"):
        return path
    if path.startswith("/izvor/"):
        source_name = path.rsplit("/", 1)[-1].strip()
        return f"/izvori?source={quote(source_name)}" if source_name else "/izvori"
    return LEGACY_ROUTE_REDIRECTS.get(path)


def _legacy_frontend_redirect(path: str):
    if _request_is_local():
        return None
    if not current_app.config.get("REDIRECT_LEGACY_FRONTEND", True):
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

    public_path = _public_site_path_for_request(request.path)
    if not public_path:
        return None

    return _legacy_frontend_redirect(request.path)


@views_bp.route("/robots.txt")
def robots_txt():
    return Response("User-agent: *\nDisallow: /api/\nAllow: /\n", mimetype="text/plain")


@views_bp.route("/og/cluster/<cluster_id>.svg")
def og_cluster_image(cluster_id: str):
    if not cluster_id or not re.match(r"^[a-f0-9]{6,64}$", cluster_id):
        return Response("Invalid cluster", status=400, mimetype="text/plain")

    conn = get_db()
    try:
        row = conn.execute("SELECT title FROM articles WHERE cluster_id = %s LIMIT 1", (cluster_id,)).fetchone()
        count_row = conn.execute("SELECT COUNT(*) FROM articles WHERE cluster_id = %s", (cluster_id,)).fetchone()
    finally:
        conn.close()

    title = row["title"] if row else "Вест"
    count = count_row[0] if count_row else 1

    safe_title = title.replace("&", "&amp;").replace('"', "&quot;")
    if len(safe_title) > 65:
        line1 = safe_title[:65]
        line2 = safe_title[65:130] + ("..." if len(safe_title) > 130 else "")
    else:
        line1 = safe_title
        line2 = ""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#1a1a1a"/>
  <rect width="1200" height="10" y="0" fill="#E63946"/>
  <text x="80" y="120" font-family="serif" font-size="32" font-weight="800" fill="#E63946" letter-spacing="2">ПРЕСЕК АНАЛИЗА</text>
  <text x="80" y="240" font-family="serif" font-size="56" font-weight="bold" fill="#ffffff">{line1}</text>
  <text x="80" y="320" font-family="serif" font-size="56" font-weight="bold" fill="#ffffff">{line2}</text>
  <text x="80" y="520" font-family="sans-serif" font-size="28" fill="#aaaaaa">{count} извори анализирани во овој кластер</text>
  <text x="1120" y="560" font-family="serif" font-size="48" font-weight="bold" fill="#E63946" text-anchor="end">пресек.мк</text>
</svg>"""
    return Response(svg, mimetype="image/svg+xml")


@views_bp.route("/og-image.svg")
def og_image():
    conn = get_db()
    try:
        row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
    finally:
        conn.close()

    count = row[0] if row else 0
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#1a1a2e"/>
  <text x="600" y="280" font-family="sans-serif" font-size="72" font-weight="bold" fill="#ffffff" text-anchor="middle">Пресек</text>
  <text x="600" y="380" font-family="sans-serif" font-size="36" fill="#aaaaaa" text-anchor="middle">{count} статии индексирани</text>
</svg>"""
    return Response(svg, mimetype="image/svg+xml")
