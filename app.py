from __future__ import annotations
import os
import time
import logging
from logging.handlers import RotatingFileHandler
from collections import defaultdict

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_compress import Compress

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

app = Flask(__name__)

_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    import sys
    log.error("FATAL: SECRET_KEY environment variable is not set. Refusing to start.")
    sys.exit(1)
app.secret_key = _secret_key

_cors_origins = os.environ.get("CORS_ORIGINS", "")
CORS(app, origins=_cors_origins.split(",") if _cors_origins else [])
Compress(app)

# Register Blueprints
app.register_blueprint(api_bp)
app.register_blueprint(views_bp)

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
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    # response.headers["Content-Security-Policy"] = (
    #     "default-src 'self'; "
    #     "script-src 'self' 'unsafe-inline'; "
    #     "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    #     "font-src 'self' https://fonts.gstatic.com; "
    #     "img-src 'self' data: https:; "
    #     "connect-src 'self'; "
    #     "frame-ancestors 'none';"
    # )
    return response

ntfy = BreakingNewsNotifier(topic=NTFY_TOPIC, threshold=3)

_prune_counter = 0
_digest_counter = 0

health.register_health_routes(app)

if __name__ == "__main__":
    init_db()
    # Start ingestion loop in a background thread
    
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
