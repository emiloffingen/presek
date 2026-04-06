from __future__ import annotations

import logging
import os

from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

import health
from config import validate_required_env
from database import init_db
from routes.views import views_bp

log = logging.getLogger("presek-legacy")

app = Flask(__name__)
app.config["PUBLIC_SITE_URL"] = os.environ.get("PUBLIC_SITE_URL", "https://presek.live")
app.config["REDIRECT_LEGACY_FRONTEND"] = os.environ.get("REDIRECT_LEGACY_FRONTEND", "1") == "1"
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.register_blueprint(views_bp)


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "presek-legacy-shim"})


health.register_health_routes(app)


if __name__ == "__main__":
    try:
        validate_required_env()
        init_db()
    except Exception as exc:
        log.error("Legacy shim startup failed: %s", exc)
        raise SystemExit(1) from exc

    app.run(
        host=os.environ.get("FLASK_BIND_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=False,
        use_reloader=False,
    )
