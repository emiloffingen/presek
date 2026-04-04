from __future__ import annotations
import os
import time
import logging
import datetime
from logging.handlers import RotatingFileHandler
from collections import defaultdict

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_compress import Compress
from werkzeug.middleware.proxy_fix import ProxyFix

class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for machine-parseable log output."""
    def format(self, record):
        import json, datetime
        log_entry = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)

# Configure logging — JSON for file (machine-parseable), human-readable for console
file_handler = RotatingFileHandler("presek.log", maxBytes=10 * 1024 * 1024, backupCount=5)
file_handler.setFormatter(JSONFormatter())

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
log = logging.getLogger("presek")

import health
from notifier import BreakingNewsNotifier
import digest as digest_module

# Import modularized components
from config import (
    NTFY_TOPIC, REFRESH_INTERVAL
)
from database import get_db, init_db, prune_db
from ingestion import ingest_feeds, ingest_diaspora_feeds
from ai_engine import auto_summarize_top_clusters
from utils import score_cluster, rank_articles_in_cluster, check_rate_limit

# Blueprints
from routes.api import api_bp
from routes.views import views_bp

from flask.json.provider import DefaultJSONProvider
from utils import DateTimeEncoder

class CustomJSONProvider(DefaultJSONProvider):
    def dumps(self, obj, **kwargs):
        kwargs.setdefault("cls", DateTimeEncoder)
        return super().dumps(obj, **kwargs)

app = Flask(__name__)
app.json = CustomJSONProvider(app)

@app.template_filter('format_time')
def format_time_filter(dt):
    if not dt: return ""
    if isinstance(dt, str):
        try:
            # Handle ISO format string from cache
            dt = datetime.datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except: return dt

    try:
        return dt.strftime('%H:%M')
    except:
        return str(dt)

@app.template_filter('briefing_format')
def briefing_format_filter(content):
    if not content: return ""
    from markupsafe import Markup
    # Convert simple markdown to HTML
    lines = content.split('\n')
    formatted_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            formatted_lines.append('<div class="my-2"></div>')
            continue

        # Headers
        if line.startswith('### '):
            formatted_lines.append(f'<h3 class="font-bold text-lg mt-6 mb-2">{line[4:]}</h3>')
        elif line.startswith('## '):
            formatted_lines.append(f'<h2 class="text-xl font-bold mt-6 mb-2">{line[3:]}</h2>')
        # Bold
        elif line.startswith('**') and line.endswith('**'):
            formatted_lines.append(f'<p class="font-bold mt-4 mb-1">{line[2:-2]}</p>')
        # Bullets
        elif line.startswith('- ') or line.startswith('• '):
            formatted_lines.append(f'<li class="ml-4 mb-1.5 text-base leading-relaxed">{line[2:]}</li>')
        else:
            formatted_lines.append(f'<p class="mb-3 text-base leading-relaxed">{line}</p>')

    return Markup('\n'.join(formatted_lines))
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    import sys
    log.error("FATAL: SECRET_KEY environment variable is not set. Refusing to start.")
    sys.exit(1)
app.secret_key = _secret_key

_cors_origins = os.environ.get("CORS_ORIGINS", "")
CORS(app, origins=_cors_origins.split(",") if _cors_origins else [])
Compress(app)
# Trust exactly one proxy hop (reverse proxy / load balancer) for correct IP forwarding
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

import json
from markupsafe import Markup

# Register Blueprints
app.register_blueprint(api_bp)
app.register_blueprint(views_bp)

# Vite Asset Helper
VITE_DEV_SERVER = os.environ.get("VITE_DEV_SERVER", "http://localhost:5173")
VITE_MANIFEST_PATH = "static/dist/.vite/manifest.json"

@app.context_processor
def vite_assets():
    def vite_asset(entry_name):
        # In development, point to the Vite dev server
        if os.environ.get("FLASK_ENV") == "development":
            if entry_name.endswith('.css'):
                return Markup(f'<link rel="stylesheet" href="{VITE_DEV_SERVER}/src/index.css">')
            return Markup(f'<script type="module" src="{VITE_DEV_SERVER}/src/{entry_name}"></script>')
        
        # In production, read from the manifest
        try:
            with open(VITE_MANIFEST_PATH, "r") as f:
                manifest = json.load(f)
            
            # Robust lookup: check for exact key, then common variations
            # Vite often uses 'index.html' for the main entry point or 'src/main.tsx'
            asset_entry = None
            if entry_name in manifest:
                asset_entry = manifest[entry_name]
            else:
                # Try common prefixes/extensions if not found
                for key in manifest:
                    if entry_name in key or key.endswith(entry_name):
                        asset_entry = manifest[key]
                        break
            
            if not asset_entry:
                # If still not found and it's a known fallback, use it
                if entry_name == 'main.js': asset_entry = manifest.get('index.html')
            
            if not asset_entry: return ""

            if entry_name.endswith('.js') or entry_name.endswith('.ts') or entry_name.endswith('.tsx'):
                return Markup(f'<script type="module" src="/static/dist/{asset_entry["file"]}"></script>')
            
            if entry_name.endswith('.css'):
                css_files = asset_entry.get('css', [])
                if not css_files:
                    # If this entry doesn't have CSS, it might be the CSS entry itself
                    if asset_entry.get('file', '').endswith('.css'):
                        return Markup(f'<link rel="stylesheet" href="/static/dist/{asset_entry["file"]}">')
                    return ""
                return Markup(f'<link rel="stylesheet" href="/static/dist/{css_files[0]}">')
        except (FileNotFoundError, json.JSONDecodeError):
            # Fallback to legacy static if manifest is missing
            if entry_name == 'main.js':
                return Markup('<script type="module" src="/static/js/main.js"></script>')
            if entry_name == 'style.css':
                return Markup('<link rel="stylesheet" href="/static/modern.css">')
        return ""
    
    return {"vite_asset": vite_asset}

@app.before_request
def rate_limit_check():
    # Only rate-limit API endpoints — HTML pages must never return JSON 429
    if not request.path.startswith('/api/'):
        return None
    if request.path in ('/api/health',):
        return None
    # ProxyFix sets request.remote_addr correctly from X-Forwarded-For
    ip = request.remote_addr or '0.0.0.0'
    if not check_rate_limit(ip):
        return jsonify({"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."}), 429

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' https:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    return response

health.register_health_routes(app)

@app.route("/sw.js")
def serve_sw():
    return send_from_directory(".", "sw.js")

@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory("static", "manifest.json")

if __name__ == "__main__":
    try:
        log.info("Initializing database...")
        init_db()
        log.info("Database initialization complete")
    except Exception as e:
        log.error(f"Failed to initialize database on startup: {e}")
        log.error("Application cannot start without database connectivity")
        import sys
        sys.exit(1)
    
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
