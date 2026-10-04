#!/usr/bin/env python3
"""Presek shared-memory HTTP relay (Tailscale-facing, token-authenticated).

Agents on hosts that do NOT have the presek repo or database credentials (for
example a tablet running opencode) reach the shared memory through this relay
instead of talking to Postgres directly. Only this process holds the DB access.

Transport: MCP "streamable HTTP" (single POST endpoint, JSON-RPC body).
Security:  requires `Authorization: Bearer <token>` where the token comes from
           the SHARED_MEMORY_TOKEN env var. Refuses to start without a token.

Run (on the Shield, inside the presek venv, cwd = repo root):
    SHARED_MEMORY_RELAY_HOST=100.77.135.12 SHARED_MEMORY_RELAY_PORT=8790 \
    SHARED_MEMORY_TOKEN=... python3 mcp/shared_memory_relay.py
"""

from __future__ import annotations

import hmac
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import the canonical tool implementation (repo-dependent flavour).
sys.path.insert(0, os.path.join(ROOT, "mcp"))
import shared_memory_mcp as mem  # noqa: E402

TOKEN = os.environ.get("SHARED_MEMORY_TOKEN", "").strip()
HOST = os.environ.get("SHARED_MEMORY_RELAY_HOST", "127.0.0.1")
PORT = int(os.environ.get("SHARED_MEMORY_RELAY_PORT", "8790"))
MAX_BODY_BYTES = int(os.environ.get("SHARED_MEMORY_RELAY_MAX_BODY", str(256 * 1024)))


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")


def _handle(msg: dict) -> dict | None:
    """Reuse the stdio server's dispatcher so behaviour stays identical."""
    return mem.handle_request(msg)


def main() -> None:
    if not TOKEN:
        sys.stderr.write(
            "[relay] refusing to start: SHARED_MEMORY_TOKEN is not set "
            "(an unauthenticated endpoint would expose the shared memory).\n"
        )
        raise SystemExit(2)

    # Minimal WSGI server; no third-party deps, runs in the presek venv.
    from wsgiref.simple_server import make_server, WSGIRequestHandler

    class Handler(WSGIRequestHandler):
        def log_message(self, *args):  # keep stdout/stderr clean
            sys.stderr.write("[relay] %s\n" % (args[0] % args[1:]))

    def app(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path not in ("/mcp", "/"):
            start_response("404 Not Found", [("Content-Type", "application/json")])
            return [_json_bytes({"error": "not found"})]

        auth = environ.get("HTTP_AUTHORIZATION", "")
        if not hmac.compare_digest(auth.encode("utf-8"), f"Bearer {TOKEN}".encode("utf-8")):
            start_response(
                "401 Unauthorized",
                [("Content-Type", "application/json"), ("WWW-Authenticate", "Bearer")],
            )
            return [_json_bytes({"error": "unauthorized"})]

        if environ.get("REQUEST_METHOD") != "POST":
            start_response("405 Method Not Allowed", [("Content-Type", "application/json")])
            return [_json_bytes({"error": "use POST"})]

        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY_BYTES:
            start_response("413 Payload Too Large", [("Content-Type", "application/json")])
            return [_json_bytes({"error": "body too large"})]
        raw = environ["wsgi.input"].read(length) if length else b""

        try:
            msg = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            start_response("400 Bad Request", [("Content-Type", "application/json")])
            return [
                _json_bytes({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"parse error: {exc}"}})
            ]

        response = _handle(msg)
        if response is None:
            # Notification: MCP expects 202 with no body.
            start_response("202 Accepted", [("Content-Type", "application/json")])
            return [b""]
        start_response("200 OK", [("Content-Type", "application/json")])
        return [_json_bytes(response)]

    sys.stderr.write(
        f"[relay] listening on http://{HOST}:{PORT}/mcp (writes={'on' if mem.writes_enabled() else 'OFF'})\n"
    )
    with make_server(HOST, PORT, app, handler_class=Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
