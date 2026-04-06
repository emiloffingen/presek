from __future__ import annotations
import os
import re
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
    NTFY_TOPIC, REFRESH_INTERVAL, validate_required_env
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
app.config["PUBLIC_SITE_URL"] = os.environ.get("PUBLIC_SITE_URL", "https://presek.live")
app.config["REDIRECT_LEGACY_FRONTEND"] = os.environ.get("REDIRECT_LEGACY_FRONTEND", "1") == "1"

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
    from markupsafe import Markup, escape
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
            formatted_lines.append(f'<h3 class="font-bold text-lg mt-6 mb-2">{escape(line[4:])}</h3>')
        elif line.startswith('## '):
            formatted_lines.append(f'<h2 class="text-xl font-bold mt-6 mb-2">{escape(line[3:])}</h2>')
        # Bold
        elif line.startswith('**') and line.endswith('**'):
            formatted_lines.append(f'<p class="font-bold mt-4 mb-1">{escape(line[2:-2])}</p>')
        # Bullets
        elif line.startswith('- ') or line.startswith('• '):
            formatted_lines.append(f'<li class="ml-4 mb-1.5 text-base leading-relaxed">{escape(line[2:])}</li>')
        else:
            formatted_lines.append(f'<p class="mb-3 text-base leading-relaxed">{escape(line)}</p>')

    return Markup('\n'.join(formatted_lines))
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    import sys
    log.error("FATAL: SECRET_KEY environment variable is not set. Refusing to start.")
    sys.exit(1)
app.secret_key = _secret_key

_public_site_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.live").rstrip("/")
_default_cors_origins = [
    _public_site_url,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4321",
    "http://127.0.0.1:4321",
]
_configured_cors_origins = [
    origin.rstrip("/")
    for origin in (o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(","))
    if origin and origin != "*"
]
_cors_origins = _configured_cors_origins or _default_cors_origins
CORS(app, resources={r"/api/*": {"origins": _cors_origins}}, supports_credentials=True)
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
def inject_now():
    return {'now': datetime.datetime.now}

@app.context_processor
def vite_assets():
    def vite_asset(entry_name):
        # In development, point to the Vite dev server
        if os.environ.get("FLASK_ENV") == "development":
            if entry_name.endswith('.css'):
                return Markup(f'<link rel="stylesheet" href="{VITE_DEV_SERVER}/src/index.css">')
            # In dev, the entry is usually src/main.tsx
            return Markup(f'<script type="module" src="{VITE_DEV_SERVER}/src/main.tsx"></script>')
        
        # In production, read from the manifest
        try:
            with open(VITE_MANIFEST_PATH, "r") as f:
                manifest = json.load(f)
            
            # Find the main entry (usually index.html or src/main.tsx)
            main_entry = manifest.get('index.html') or manifest.get('src/main.tsx')
            
            if not main_entry:
                # Fallback: search for any entry that is an entry point
                for k, v in manifest.items():
                    if v.get('isEntry'):
                        main_entry = v
                        break
            
            if not main_entry: return ""

            # If they want CSS
            if entry_name.endswith('.css'):
                css_files = main_entry.get('css', [])
                if css_files:
                    return Markup(f'<link rel="stylesheet" href="/static/dist/{css_files[0]}">')
                return ""
            
            # If they want JS (the module)
            return Markup(f'<script type="module" src="/static/dist/{main_entry["file"]}"></script>')
            
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
    # Only rate-limit expensive AI endpoints — browsing endpoints must stay available.
    if not request.path.startswith('/api/'):
        return None
    expensive_paths = {
        '/api/chat_cluster',
        '/api/chat/stream',
    }
    is_cluster_ask = re.match(r'^/api/cluster/[a-f0-9]{6,64}/ask$', request.path or '')
    if request.path not in expensive_paths and not is_cluster_ask:
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
        validate_required_env()
        log.info("Initializing database...")
        init_db()
        log.info("Database initialization complete")
    except Exception as e:
        log.error(f"Failed to initialize database on startup: {e}")
        log.error("Application cannot start without database connectivity")
        import sys
        sys.exit(1)
    
    app.run(
        host=os.environ.get("FLASK_BIND_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=False,
        use_reloader=False,
    )
