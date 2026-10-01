#!/usr/bin/env python3
"""Presek ops MCP server (stdio transport, dependency-free).

Speaks newline-delimited JSON-RPC 2.0 over stdin/stdout. All diagnostics go to
stderr so stdout stays a clean JSON-RPC stream.

Protocol version: 2025-06-18 (also accepts 2024-11-05 clients).

Tools:
  presek_health          overall service health + AI quota budgets
  presek_ops_snapshot    queues, freshness, synthesis quality
  presek_queue_status    Celery queue depths with warn/critical state
  presek_recent_logs     tail a whitelisted service log (filtered)
  presek_db_query        read-only SQL against the primary database
  presek_ai_quota        per-provider daily AI request budgets
  presek_version         running backend version

Run:  python3 mcp/presek_mcp.py     (cwd must be the presek root)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = {"2025-06-18", "2025-03-26", "2024-11-05"}
SERVER_NAME = "presek-ops"
SERVER_VERSION = "1.0.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "logs")

LOG_SERVICES = {
    "astro": "astro.log",
    "fastapi": "fastapi.log",
    "worker": "worker.log",
    "beat": "beat.log",
    "watchdog": "watchdog.log",
    "cloudflared": "cloudflared.log",
    "redis": "redis.log",
    "deploy": "deploy.log",
}

MAX_LOG_LINES = 500
DEFAULT_LOG_LINES = 40
MAX_SQL_ROWS = 200

_WRITE_SQL_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|comment|merge|call|copy|vacuum|reindex)\b",
    re.IGNORECASE,
)


def log(msg: str) -> None:
    """Diagnostics only — MUST go to stderr."""
    sys.stderr.write(f"[presek-mcp] {msg}\n")
    sys.stderr.flush()


# --------------------------------------------------------------------------
# Backend access (lazy; the server must start even if the stack is down)
# --------------------------------------------------------------------------


def _bootstrap() -> None:
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        for raw in open(env_path, encoding="utf-8"):
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_env() -> dict:
    env = {}
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        for raw in open(env_path, encoding="utf-8"):
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def tool_health() -> dict:
    import urllib.request

    env = _load_env()
    # PUBLIC_API_URL is a browser-relative path ("/api"); prefer the absolute internal URL.
    api = next(
        (u for u in (env.get("INTERNAL_API_URL"), env.get("PUBLIC_API_URL")) if u and u.startswith("http")),
        "http://127.0.0.1:5001/api",
    )
    if api.endswith("/"):
        api = api[:-1]
    url = f"{api}/health"
    out: dict = {"url": url}
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            out["status_code"] = resp.status
            out["body"] = json.loads(resp.read().decode("utf-8"))
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out


def tool_ops_snapshot() -> dict:
    _bootstrap()
    try:
        from core.ops_snapshot import build_ops_snapshot  # type: ignore
    except Exception:
        build_ops_snapshot = None  # type: ignore
    if build_ops_snapshot is not None:
        try:
            import asyncio

            result = build_ops_snapshot()
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
            return result
        except Exception as exc:
            log(f"ops_snapshot failed, falling back: {exc}")
    # Fallback: compose from the health endpoint only.
    return {"source": "fallback", "health": tool_health()}


def tool_queue_status() -> dict:
    _bootstrap()
    try:
        import core.health as health  # type: ignore

        return health._probe_celery_queue()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def tool_recent_logs(service: str = "worker", lines: int = DEFAULT_LOG_LINES, grep: str | None = None) -> dict:
    filename = LOG_SERVICES.get(service)
    if not filename:
        return {"error": f"unknown service '{service}'", "allowed": sorted(LOG_SERVICES)}
    try:
        lines = max(1, min(int(lines), MAX_LOG_LINES))
    except (TypeError, ValueError):
        lines = DEFAULT_LOG_LINES
    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path):
        return {"error": f"log not found: {path}"}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            tail = fh.readlines()[-lines * 4 :]
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    if grep:
        try:
            pattern = re.compile(grep)
            tail = [ln for ln in tail if pattern.search(ln)]
        except re.error as exc:
            return {"error": f"bad grep regex: {exc}"}
    return {"service": service, "path": path, "lines": [ln.rstrip("\n") for ln in tail[-lines:]]}


def tool_db_query(sql: str, limit: int = 50) -> dict:
    sql = (sql or "").strip().rstrip(";")
    if not sql:
        return {"error": "empty sql"}
    if _WRITE_SQL_PATTERN.search(sql):
        return {"error": "only read-only SELECT/WITH/SHOW/EXPLAIN queries are allowed"}
    if not re.match(r"^(select|with|show|explain|table)\b", sql, re.IGNORECASE):
        return {"error": "query must start with SELECT, WITH, SHOW, EXPLAIN or TABLE"}
    try:
        limit = max(1, min(int(limit), MAX_SQL_ROWS))
    except (TypeError, ValueError):
        limit = 50
    if " limit " not in sql.lower():
        sql = f"{sql} LIMIT {limit}"
    _bootstrap()
    try:
        from core.database import db_manager  # type: ignore

        rows = db_manager.execute(sql, read_only=True)
        return {"row_count": len(rows or []), "rows": rows or []}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def tool_ai_quota() -> dict:
    _bootstrap()
    try:
        from core.ai_quota import snapshot  # type: ignore

        return snapshot()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def tool_version() -> dict:
    _bootstrap()
    try:
        from core.config import APP_VERSION  # type: ignore

        return {"version": APP_VERSION}
    except Exception:
        version_file = os.path.join(ROOT, "VERSION")
        if os.path.exists(version_file):
            return {"version": open(version_file).read().strip()}
        return {"version": "unknown"}


# --------------------------------------------------------------------------
# Tool registry (JSON Schema for MCP tools/list)
# --------------------------------------------------------------------------

TOOLS: dict[str, dict] = {
    "presek_health": {
        "description": "Overall Presek service health (database, redis, queues) and AI quota budgets.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": lambda args: tool_health(),
    },
    "presek_ops_snapshot": {
        "description": "Combined operational snapshot: queues, freshness, synthesis quality and alerts.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": lambda args: tool_ops_snapshot(),
    },
    "presek_queue_status": {
        "description": "Celery queue depths with warn/critical/degraded state per queue.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": lambda args: tool_queue_status(),
    },
    "presek_recent_logs": {
        "description": "Tail one of the whitelisted service logs, optionally filtered by a regex.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": sorted(LOG_SERVICES)},
                "lines": {"type": "integer", "minimum": 1, "maximum": MAX_LOG_LINES, "default": DEFAULT_LOG_LINES},
                "grep": {"type": "string", "description": "Optional Python regex filter applied to tailed lines."},
            },
            "required": ["service"],
            "additionalProperties": False,
        },
        "handler": lambda args: tool_recent_logs(
            args.get("service", "worker"), args.get("lines", DEFAULT_LOG_LINES), args.get("grep")
        ),
    },
    "presek_db_query": {
        "description": "Run a READ-ONLY SQL query (SELECT/WITH/SHOW/EXPLAIN) against the primary database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_SQL_ROWS, "default": 50},
            },
            "required": ["sql"],
            "additionalProperties": False,
        },
        "handler": lambda args: tool_db_query(args.get("sql", ""), args.get("limit", 50)),
    },
    "presek_ai_quota": {
        "description": "Per-provider daily AI request budgets (limit + used) shared across hosts.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": lambda args: tool_ai_quota(),
    },
    "presek_version": {
        "description": "Running Presek backend version.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": lambda args: tool_version(),
    },
}


# --------------------------------------------------------------------------
# JSON-RPC dispatch
# --------------------------------------------------------------------------


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _tool_listing() -> list[dict]:
    return [
        {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
        for name, spec in TOOLS.items()
    ]


def handle_request(msg: dict) -> dict | None:
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        return _result(
            req_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method == "ping":
        return _result(req_id, {})

    if method == "tools/list":
        return _result(req_id, {"tools": _tool_listing()})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        spec = TOOLS.get(name)
        if spec is None:
            return _result(
                req_id,
                {
                    "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                    "isError": True,
                },
            )
        try:
            payload = spec["handler"](args)
            is_error = isinstance(payload, dict) and "error" in payload and len(payload) == 1
            text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        except Exception as exc:  # never crash the stream
            text = json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
            is_error = True
        return _result(req_id, {"content": [{"type": "text", "text": text}], "isError": is_error})

    if method == "prompts/list":
        return _result(req_id, {"prompts": []})

    if method == "resources/list":
        return _result(req_id, {"resources": []})

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None  # notification: no response

    return _error(req_id, -32601, f"Method not found: {method}")


def main() -> None:
    log(f"start (root={ROOT}, pid={os.getpid()})")
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            log(f"invalid JSON on stdin: {exc}")
            continue
        try:
            response = handle_request(msg)
        except Exception as exc:  # pragma: no cover - defensive
            log(f"handler crashed: {exc}")
            response = _error(msg.get("id"), -32603, f"Internal error: {exc}")
        if response is None:
            continue
        try:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except (BrokenPipeError, ValueError):
            break
    log("stdin closed; exiting")


if __name__ == "__main__":
    main()
